"""
Web API Connector v2.0 — ACTIF (version de production).

Statut : enregistré dans le registry sous "web_api", importé par
         internal/connector/__init__.py. Remplace la v1 (archivée dans
         _archive/web_api_v1/) depuis juillet 2026.

Fonctionnalités vs v1 :
  - Rate limiting interne (token bucket)
  - Circuit breaker (fail-fast sur API down)
  - Pagination cursor + offset (en plus de Link header)
  - Extraction incrémentale (state management)
  - Error classification (retriable vs fatal)

Politiques : plugins/web_api_policies/ (RateLimitPolicy, CircuitBreakerPolicy,
             StateManager, ErrorClassifier).
"""

from typing import Iterator, Dict, Any, Optional, List
import requests
import time
import jsonpath_ng
from requests.exceptions import RequestException, Timeout

from hydra_etl.plugins.auth_providers import AuthProvider, AuthenticationError
from hydra_etl.plugins.pagination_strategies import PaginationStrategy
from hydra_etl.plugins.retry_policies import RetryPolicy


class WebAPIConnector:
    """
    Connecteur Web API v2.0 - Production-Ready.
    
    Nouvelles fonctionnalités Sprint 2:
    - Rate limiting interne avec token bucket
    - Circuit breaker pour fail-fast
    - Support pagination cursor + offset
    - Extraction incrémentale avec state file
    - Classification erreurs intelligente
    
    Configuration DSL complète:
        sources:
          api:
            type: web_api
            connection:
              base_url: https://api.example.com
              timeout_connect: 10
              timeout_read: 30
            extract:
              endpoint: /data
              json_path: $.items[*]
              method: GET
            auth:
              type: oauth2
              client_id: ${ENV:CLIENT_ID}
              client_secret: ${ENV:SECRET}
              token_url: https://api.example.com/token
            pagination:
              type: cursor  # ou offset, next_link
              cursor_field: paging.next
              cursor_param: after
              page_size: 100
            rate_limit:
              requests_per_second: 10
              burst: 50
            circuit_breaker:
              failure_threshold: 5
              timeout: 60
            incremental:
              enabled: true
              state_field: updated_at
              state_file: .hydra/state/api.json
            retry:
              max_attempts: 3
              initial_backoff: 1.0
    """
    
    def __init__(
        self,
        name: str,
        base_url: str,
        auth_provider: AuthProvider,
        pagination_strategy: Optional[PaginationStrategy] = None,
        retry_policy: Optional[RetryPolicy] = None,
        rate_limit_policy: Optional['RateLimitPolicy'] = None,
        circuit_breaker: Optional['CircuitBreakerPolicy'] = None,
        state_manager: Optional['StateManager'] = None,
        error_classifier: Optional['ErrorClassifier'] = None,
        timeout_connect: int = 10,
        timeout_read: int = 30,
        json_path: str = "$[*]",
        batch_size: int = 1000
    ):
        """
        Initialise Web API Connector v2.0.
        
        Args:
            name: Nom connecteur
            base_url: URL base API
            auth_provider: Stratégie auth
            pagination_strategy: Stratégie pagination (optionnel)
            retry_policy: Politique retry (optionnel)
            rate_limit_policy: Politique rate limit (optionnel, NEW)
            circuit_breaker: Circuit breaker (optionnel, NEW)
            state_manager: Gestionnaire état incrémental (optionnel, NEW)
            error_classifier: Classificateur erreurs (optionnel, NEW)
            timeout_connect: Timeout connexion
            timeout_read: Timeout lecture
            json_path: Expression JSONPath
            batch_size: Taille batches
        """
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.auth_provider = auth_provider
        self.pagination_strategy = pagination_strategy
        self.retry_policy = retry_policy or RetryPolicy()
        self.rate_limit_policy = rate_limit_policy
        self.circuit_breaker = circuit_breaker
        self.state_manager = state_manager
        self.error_classifier = error_classifier or ErrorClassifier()
        self.timeout_connect = timeout_connect
        self.timeout_read = timeout_read
        self.json_path = json_path
        self.batch_size = batch_size
        
        # Compiler JSONPath
        try:
            self._jsonpath_expr = jsonpath_ng.parse(json_path)
        except Exception as e:
            raise ValueError(f"Invalid JSONPath '{json_path}': {e}") from e
        
        # Valider
        self._validate()
    
    def _validate(self) -> None:
        """Valide configuration (fail-fast)."""
        if not self.base_url:
            raise ValueError(f"Connector '{self.name}': base_url required")
        
        if not self.base_url.startswith(("http://", "https://")):
            raise ValueError(f"Connector '{self.name}': base_url must be http/https")
        
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
        
        if self.rate_limit_policy:
            self.rate_limit_policy.validate()
        
        if self.circuit_breaker:
            self.circuit_breaker.validate()
        
        if self.error_classifier:
            self.error_classifier.validate()
    
    def test_connection(self) -> bool:
        """
        Test connectivité API.
        
        Returns:
            True si OK.
        
        Raises:
            ConnectionError: Si échec.
        """
        try:
            headers = self.auth_provider.get_headers()
            
            response = requests.head(
                self.base_url,
                headers=headers,
                timeout=(self.timeout_connect, self.timeout_read),
                allow_redirects=True
            )
            
            if response.status_code < 500:
                return True
            
            raise ConnectionError(f"Server error {response.status_code}")
        
        except RequestException as e:
            raise ConnectionError(f"Failed to connect: {e}") from e
    
    def extract_batches(
        self,
        endpoint: str,
        method: str = "GET",
        query_params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Iterator[List[Dict[str, Any]]]:
        """
        Extrait données par batches avec pagination.
        
        NOUVEAU v2.0:
        - Rate limiting automatique
        - Circuit breaker protection
        - Extraction incrémentale
        - Error classification
        
        Args:
            endpoint: Endpoint à appeler
            method: Méthode HTTP
            query_params: Query params
            headers: Headers custom
        
        Yields:
            Batches de dicts.
        """
        # Normaliser endpoint
        if not endpoint.startswith("/"):
            endpoint = f"/{endpoint}"
        
        url = f"{self.base_url}{endpoint}"
        
        # Headers base
        request_headers = self.auth_provider.get_headers()
        if headers:
            request_headers.update(headers)
        
        # Query params base
        params = dict(query_params) if query_params else {}
        
        # Ajouter filtre incrémental si activé
        if self.state_manager:
            last_state = self.state_manager.load_state()
            if last_state is not None:
                # Ajouter filtre (ex: updated_at > last_state)
                state_field = self.state_manager.state_field
                params[f"{state_field}_gt"] = last_state
        
        # Params pagination initiale
        if self.pagination_strategy:
            params.update(self.pagination_strategy.get_initial_params())
        
        # Accumulateur batching
        accumulated_items: List[Dict[str, Any]] = []
        all_items: List[Dict[str, Any]] = []  # Pour state update
        
        # Loop pagination
        page_num = 0
        while True:
            page_num += 1
            
            # Fetch page avec rate limit + circuit breaker + retry
            response_data, response_headers = self._fetch_page_protected(
                url=url,
                method=method,
                params=params,
                headers=request_headers
            )
            
            # Extraire items
            items = self._extract_items(response_data)
            
            # Accumuler
            accumulated_items.extend(items)
            all_items.extend(items)
            
            # Yield batch si taille atteinte
            while len(accumulated_items) >= self.batch_size:
                batch = accumulated_items[:self.batch_size]
                accumulated_items = accumulated_items[self.batch_size:]
                yield batch
            
            # Vérifier pagination
            if not self.pagination_strategy:
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
                params = {}
            elif pagination_state.next_params:
                params.update(pagination_state.next_params)
        
        # Yield items restants
        if accumulated_items:
            yield accumulated_items
        
        # Mettre à jour state si incrémental
        if self.state_manager and all_items:
            self.state_manager.update_state_from_items(all_items)
    
    def _fetch_page_protected(
        self,
        url: str,
        method: str,
        params: Dict[str, Any],
        headers: Dict[str, str]
    ) -> tuple[Any, Dict[str, str]]:
        """
        Fetch page avec protection complète (NEW v2.0).
        
        Protection layers:
        1. Rate limiting (éviter ban)
        2. Circuit breaker (fail-fast)
        3. Retry avec backoff
        4. Error classification
        
        Returns:
            (response_data, response_headers)
        """
        # Layer 1: Rate limiting
        if self.rate_limit_policy:
            try:
                self.rate_limit_policy.acquire()
            except Exception as e:
                raise ConnectionError(f"Rate limit exceeded: {e}") from e
        
        # Layer 2: Circuit breaker + retry
        if self.circuit_breaker:
            return self.circuit_breaker.call(
                self._fetch_with_retry,
                url, method, params, headers
            )
        else:
            return self._fetch_with_retry(url, method, params, headers)
    
    def _fetch_with_retry(
        self,
        url: str,
        method: str,
        params: Dict[str, Any],
        headers: Dict[str, str]
    ) -> tuple[Any, Dict[str, str]]:
        """Fetch avec retry (identique v1.0 + error classification)."""
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
                
                # Classification erreurs (NEW)
                if not (200 <= response.status_code < 300):
                    if self.error_classifier.is_fatal(response.status_code):
                        # Erreur fatale = arrêt immédiat
                        if response.status_code in (401, 403):
                            self.auth_provider.on_auth_failure(
                                status_code=response.status_code,
                                response_body=response.text
                            )
                            raise AuthenticationError(
                                f"Authentication failed ({response.status_code})"
                            )
                        
                        raise ValueError(
                            f"Fatal error {response.status_code}: {response.text[:200]}"
                        )
                    
                    # Erreur retriable
                    if self.error_classifier.is_retriable(response.status_code):
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
                                f"Retry {attempt}/{self.retry_policy.max_attempts} "
                                f"after {response.status_code} (wait {wait_time:.1f}s)"
                            )
                            
                            time.sleep(wait_time)
                            continue
                        
                        raise ConnectionError(
                            f"Max retries reached after {response.status_code}"
                        )
                
                # Succès
                try:
                    data = response.json()
                except Exception as e:
                    raise ValueError(f"Invalid JSON: {e}") from e
                
                return data, dict(response.headers)
            
            except Timeout as e:
                if self.retry_policy.should_retry(status_code=504, attempt=attempt):
                    wait_time = self.retry_policy.get_wait_time(status_code=504, attempt=attempt)
                    time.sleep(wait_time)
                    continue
                
                raise ConnectionError(f"Timeout after {attempt} attempts") from e
            
            except (AuthenticationError, ValueError):
                raise
            
            except RequestException as e:
                last_exception = e
                
                if self.retry_policy.should_retry(status_code=503, attempt=attempt):
                    wait_time = self.retry_policy.get_wait_time(status_code=503, attempt=attempt)
                    time.sleep(wait_time)
                    continue
                
                raise ConnectionError(f"Network error: {e}") from last_exception
    
    def _parse_retry_after(self, headers: Dict[str, str]) -> Optional[int]:
        """Parse header Retry-After."""
        retry_after = headers.get("Retry-After") or headers.get("retry-after")
        
        if not retry_after:
            return None
        
        try:
            return int(retry_after)
        except ValueError:
            return None
    
    def _extract_items(self, response_data: Any) -> List[Dict[str, Any]]:
        """Extrait items via JSONPath."""
        matches = self._jsonpath_expr.find(response_data)
        
        if not matches:
            return []
        
        items = []
        for match in matches:
            value = match.value
            
            if not isinstance(value, dict):
                raise ValueError(
                    f"JSONPath returned non-dict. Expected dict, got {type(value).__name__}"
                )
            
            items.append(value)
        
        return items


# Politiques Web API (rate limit, circuit breaker, state, error classifier)
from hydra_etl.plugins.web_api_policies import (
    RateLimitPolicy,
    CircuitBreakerPolicy,
    StateManager,
    ErrorClassifier,
)
