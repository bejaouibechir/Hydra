from typing import Iterator, Dict, Any, Optional, List
import requests
import time
import jsonpath_ng
from requests.exceptions import RequestException, Timeout

from plugins.auth_providers import AuthProvider, AuthenticationError
from plugins.pagination_strategies import PaginationStrategy
from plugins.retry_policies import RetryPolicy


class WebAPIConnector:
    """
    Connecteur pour APIs REST avec résilience et pagination.
    
    Configuration DSL minimale:
        sources:
          github_repos:
            type: web_api
            connection:
              base_url: https://api.github.com
            extract:
              endpoint: /users/octocat/repos
              json_path: $[*]  # Extrait tous items du array root
            auth:
              type: bearer
              token: ${ENV:GITHUB_TOKEN}
    
    Configuration complète:
        sources:
          stripe_api:
            type: web_api
            connection:
              base_url: https://api.stripe.com/v1
              timeout_connect: 10
              timeout_read: 30
            extract:
              endpoint: /customers
              json_path: $.data[*]
              method: GET
            auth:
              type: oauth2
              client_id: ${ENV:STRIPE_CLIENT_ID}
              client_secret: ${ENV:STRIPE_SECRET}
              token_url: https://api.stripe.com/oauth/token
            pagination:
              type: next_link
              page_size: 100
            retry:
              max_attempts: 3
              initial_backoff: 1.0
    
    Exemples d'usage:
        >>> from policies.api_key_auth import APIKeyAuth
        >>> from policies.next_link_pagination import NextLinkPagination
        >>> 
        >>> connector = WebAPIConnector(
        ...     name="github_api",
        ...     base_url="https://api.github.com",
        ...     auth_provider=APIKeyAuth(key="ghp_..."),
        ...     pagination_strategy=NextLinkPagination(page_size=100)
        ... )
        >>> 
        >>> for batch in connector.extract_batches(endpoint="/users/octocat/repos"):
        ...     for item in batch:
        ...         print(item["name"])
    """
    
    def __init__(
        self,
        name: str,
        base_url: str,
        auth_provider: AuthProvider,
        pagination_strategy: Optional[PaginationStrategy] = None,
        retry_policy: Optional[RetryPolicy] = None,
        timeout_connect: int = 10,
        timeout_read: int = 30,
        json_path: str = "$[*]",
        batch_size: int = 1000
    ):
        """
        Initialise le connecteur Web API.
        
        Args:
            name: Nom du connecteur (pour logs)
            base_url: URL de base de l'API (ex: https://api.github.com)
            auth_provider: Stratégie d'authentification (AuthProvider)
            pagination_strategy: Stratégie de pagination (optionnel, None = pas de pagination)
            retry_policy: Politique de retry (optionnel, None = pas de retry)
            timeout_connect: Timeout connexion TCP en secondes (défaut: 10)
            timeout_read: Timeout lecture réponse en secondes (défaut: 30)
            json_path: Expression JSONPath pour extraire items (défaut: $[*])
            batch_size: Taille des batches retournés (défaut: 1000)
        
        Raises:
            ValueError: Si configuration invalide.
        """
        self.name = name
        self.base_url = base_url.rstrip("/")  # Normaliser URL
        self.auth_provider = auth_provider
        self.pagination_strategy = pagination_strategy
        self.retry_policy = retry_policy or RetryPolicy()  # Retry par défaut
        self.timeout_connect = timeout_connect
        self.timeout_read = timeout_read
        self.json_path = json_path
        self.batch_size = batch_size
        
        # Compiler JSONPath
        try:
            self._jsonpath_expr = jsonpath_ng.parse(json_path)
        except Exception as e:
            raise ValueError(f"Invalid JSONPath expression '{json_path}': {e}") from e
        
        # Valider configuration
        self._validate()
    
    def _validate(self) -> None:
        """
        Valide la configuration au démarrage (fail-fast).
        
        Raises:
            ValueError: Si configuration invalide.
        """
        if not self.base_url:
            raise ValueError(f"Connector '{self.name}': base_url is required")
        
        if not self.base_url.startswith(("http://", "https://")):
            raise ValueError(
                f"Connector '{self.name}': base_url must be http/https, got: {self.base_url}"
            )
        
        if self.timeout_connect <= 0 or self.timeout_read <= 0:
            raise ValueError(f"Connector '{self.name}': timeouts must be > 0")
        
        if self.batch_size <= 0:
            raise ValueError(f"Connector '{self.name}': batch_size must be > 0")
        
        # Valider policies
        self.auth_provider.validate()
        
        if self.pagination_strategy:
            self.pagination_strategy.validate()
        
        if self.retry_policy:
            self.retry_policy.validate()
    
    def test_connection(self) -> bool:
        """
        Test la connectivité à l'API.
        
        Fait une requête HEAD ou GET simple pour vérifier:
        - DNS résolu
        - Serveur accessible
        - Auth fonctionnelle
        
        Returns:
            True si connexion OK.
        
        Raises:
            ConnectionError: Si impossible de se connecter.
        """
        try:
            # Tenter HEAD sur base_url (plus léger que GET)
            headers = self.auth_provider.get_headers()
            
            response = requests.head(
                self.base_url,
                headers=headers,
                timeout=(self.timeout_connect, self.timeout_read),
                allow_redirects=True
            )
            
            # 2xx ou 3xx = OK
            # 401/403 = auth incorrecte mais serveur accessible
            if response.status_code < 500:
                return True
            
            raise ConnectionError(
                f"Connector '{self.name}': Server error {response.status_code}"
            )
        
        except RequestException as e:
            raise ConnectionError(
                f"Connector '{self.name}': Failed to connect to {self.base_url}: {e}"
            ) from e
    
    def extract_batches(
        self,
        endpoint: str,
        method: str = "GET",
        query_params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Iterator[List[Dict[str, Any]]]:
        """
        Extrait données de l'API par batches avec pagination automatique.
        
        Args:
            endpoint: Endpoint à appeler (ex: /users/octocat/repos)
            method: Méthode HTTP (défaut: GET)
            query_params: Query params additionnels
            headers: Headers HTTP additionnels
        
        Yields:
            Batches de dicts (items extraits via JSONPath).
        
        Examples:
            >>> for batch in connector.extract_batches(endpoint="/repos"):
            ...     print(f"Got {len(batch)} items")
            ...     for item in batch:
            ...         process(item)
        """
        # Normaliser endpoint
        if not endpoint.startswith("/"):
            endpoint = f"/{endpoint}"
        
        # Construire URL complète
        url = f"{self.base_url}{endpoint}"
        
        # Headers de base (auth + customs)
        request_headers = self.auth_provider.get_headers()
        if headers:
            request_headers.update(headers)
        
        # Query params de base (pagination + customs)
        params = dict(query_params) if query_params else {}
        
        if self.pagination_strategy:
            params.update(self.pagination_strategy.get_initial_params())
        
        # Accumulator pour batching
        accumulated_items: List[Dict[str, Any]] = []
        
        # Loop de pagination
        page_num = 0
        while True:
            page_num += 1
            
            # Fetch page avec retry
            response_data, response_headers = self._fetch_with_retry(
                url=url,
                method=method,
                params=params,
                headers=request_headers
            )
            
            # Extraire items via JSONPath
            items = self._extract_items(response_data)
            
            # Accumuler items
            accumulated_items.extend(items)
            
            # Yield batch si taille atteinte
            while len(accumulated_items) >= self.batch_size:
                batch = accumulated_items[:self.batch_size]
                accumulated_items = accumulated_items[self.batch_size:]
                yield batch
            
            # Vérifier s'il reste des pages
            if not self.pagination_strategy:
                # Pas de pagination = une seule page
                break
            
            pagination_state = self.pagination_strategy.get_next_page(
                response_data=response_data,
                response_headers=response_headers,
                current_url=url
            )
            
            if not pagination_state.has_more:
                break
            
            # Préparer next request
            if pagination_state.next_url:
                url = pagination_state.next_url
                params = {}  # URL complète fournie
            elif pagination_state.next_params:
                params.update(pagination_state.next_params)
        
        # Yield items restants
        if accumulated_items:
            yield accumulated_items
    
    def _fetch_with_retry(
        self,
        url: str,
        method: str,
        params: Dict[str, Any],
        headers: Dict[str, str]
    ) -> tuple[Any, Dict[str, str]]:
        """
        Fetch URL avec retry automatique sur erreurs transitoires.
        
        Args:
            url: URL complète
            method: Méthode HTTP
            params: Query params
            headers: Headers HTTP
        
        Returns:
            (response_data, response_headers)
        
        Raises:
            AuthenticationError: Si erreur auth (401, 403)
            ConnectionError: Si toutes les tentatives échouent
        """
        attempt = 0
        last_exception = None
        
        while True:
            attempt += 1
            
            try:
                response = requests.request(
                    method=method,
                    url=url,
                    params=params,
                    headers=headers,
                    timeout=(self.timeout_connect, self.timeout_read)
                )
                
                # Erreurs auth = fatal, pas de retry
                if response.status_code in (401, 403):
                    self.auth_provider.on_auth_failure(
                        status_code=response.status_code,
                        response_body=response.text
                    )
                    raise AuthenticationError(
                        f"Connector '{self.name}': Authentication failed ({response.status_code}). "
                        f"Check credentials."
                    )
                
                # Erreurs client (4xx sauf 429) = fatal
                if 400 <= response.status_code < 500 and response.status_code != 429:
                    raise ValueError(
                        f"Connector '{self.name}': Client error {response.status_code}. "
                        f"URL: {url}, Response: {response.text[:200]}"
                    )
                
                # Erreurs serveur (5xx) ou 429 = retriable
                if response.status_code >= 500 or response.status_code == 429:
                    # Parser Retry-After header si présent
                    retry_after = self._parse_retry_after(response.headers)
                    
                    if self.retry_policy.should_retry(
                        status_code=response.status_code,
                        attempt=attempt,
                        retry_after=retry_after
                    ):
                        wait_time = self.retry_policy.get_wait_time(
                            status_code=response.status_code,
                            attempt=attempt,
                            retry_after=retry_after
                        )
                        
                        print(
                            f"Connector '{self.name}': Retry {attempt}/{self.retry_policy.max_attempts} "
                            f"after {response.status_code} (wait {wait_time:.1f}s)"
                        )
                        
                        time.sleep(wait_time)
                        continue  # Retry
                    
                    # Max retries atteint
                    raise ConnectionError(
                        f"Connector '{self.name}': Max retries ({self.retry_policy.max_attempts}) "
                        f"reached after {response.status_code}. URL: {url}"
                    )
                
                # 2xx = succès
                if 200 <= response.status_code < 300:
                    try:
                        data = response.json()
                    except Exception as e:
                        raise ValueError(
                            f"Connector '{self.name}': Invalid JSON response: {e}"
                        ) from e
                    
                    return data, dict(response.headers)
                
                # Autre status code inattendu
                raise ValueError(
                    f"Connector '{self.name}': Unexpected status {response.status_code}"
                )
            
            except Timeout as e:
                # Timeout = retriable
                if self.retry_policy.should_retry(status_code=504, attempt=attempt):
                    wait_time = self.retry_policy.get_wait_time(status_code=504, attempt=attempt)
                    
                    print(
                        f"Connector '{self.name}': Retry {attempt}/{self.retry_policy.max_attempts} "
                        f"after timeout (wait {wait_time:.1f}s)"
                    )
                    
                    time.sleep(wait_time)
                    continue
                
                raise ConnectionError(
                    f"Connector '{self.name}': Timeout after {attempt} attempts"
                ) from e
            
            except (AuthenticationError, ValueError):
                # Erreurs fatales = propager immédiatement
                raise
            
            except RequestException as e:
                # Autres erreurs réseau = retriable
                last_exception = e
                
                if self.retry_policy.should_retry(status_code=503, attempt=attempt):
                    wait_time = self.retry_policy.get_wait_time(status_code=503, attempt=attempt)
                    
                    print(
                        f"Connector '{self.name}': Retry {attempt}/{self.retry_policy.max_attempts} "
                        f"after network error (wait {wait_time:.1f}s)"
                    )
                    
                    time.sleep(wait_time)
                    continue
                
                raise ConnectionError(
                    f"Connector '{self.name}': Network error after {attempt} attempts: {e}"
                ) from last_exception
    
    def _parse_retry_after(self, headers: Dict[str, str]) -> Optional[int]:
        """
        Parse header Retry-After (RFC 7231).
        
        Formats supportés:
        - Retry-After: 120 (secondes)
        - Retry-After: Wed, 21 Oct 2015 07:28:00 GMT (date HTTP)
        
        Args:
            headers: Headers HTTP de la réponse
        
        Returns:
            Nombre de secondes à attendre, ou None si absent/invalide.
        """
        retry_after = headers.get("Retry-After") or headers.get("retry-after")
        
        if not retry_after:
            return None
        
        # Tenter de parser comme int (secondes)
        try:
            return int(retry_after)
        except ValueError:
            # Format date HTTP non supporté dans MVP
            # TODO Sprint 2: parser date HTTP
            return None
    
    def _extract_items(self, response_data: Any) -> List[Dict[str, Any]]:
        """
        Extrait items depuis réponse JSON via JSONPath.
        
        Args:
            response_data: Réponse JSON parsée
        
        Returns:
            Liste d'items (dicts).
        
        Raises:
            ValueError: Si JSONPath ne matche rien ou retourne types invalides.
        """
        matches = self._jsonpath_expr.find(response_data)
        
        if not matches:
            # JSONPath ne matche rien = peut-être fin de pagination
            return []
        
        items = []
        for match in matches:
            value = match.value
            
            # Valider que chaque item est un dict
            if not isinstance(value, dict):
                raise ValueError(
                    f"Connector '{self.name}': JSONPath returned non-dict item. "
                    f"Expected dict, got {type(value).__name__}. "
                    f"Check json_path configuration."
                )
            
            items.append(value)
        
        return items
