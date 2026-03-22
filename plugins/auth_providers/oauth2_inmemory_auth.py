"""
OAuth2 In-Memory Authentication - Client Credentials avec cache mémoire.

Implémentation MVP pour OAuth2. Cache en mémoire, suffisant pour jobs batch.
Migration future vers SharedAuthService ou EventStreamAuth possible sans
casser le code existant grâce à l'interface AuthProvider.

Cas d'usage:
- OAuth2 Client Credentials flow
- Tokens avec expiration
- Jobs batch (pas de partage de tokens entre workers)
"""

from typing import Dict, Optional
import time
import requests
from .auth_provider import AuthProvider, AuthenticationError


class OAuth2InMemoryAuth(AuthProvider):
    """
    Authentification OAuth2 avec cache en mémoire.
    
    Implémente le flow "Client Credentials":
    1. POST vers token_url avec client_id/client_secret
    2. Cache le token avec son expiration
    3. Refresh automatique avant expiration
    
    Configuration DSL:
        sources:
          stripe_api:
            type: web_api
            auth:
              type: oauth2
              client_id: ${ENV:STRIPE_CLIENT_ID}
              client_secret: ${ENV:STRIPE_SECRET}
              token_url: https://api.stripe.com/oauth/token
              scope: read_data  # optionnel
    
    Limitations MVP:
    - Cache en mémoire (perdu au redémarrage)
    - Pas de partage entre workers
    - Thread-safe basique (suffisant pour batch)
    
    Migration future:
    - Sprint 5: Remplacer par SharedAuthService (cache Redis)
    - v2.0: EventStreamAuthProvider (Kafka)
    """
    
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        token_url: str,
        scope: Optional[str] = None,
        token_expiry_margin: int = 60
    ):
        """
        Initialise OAuth2 avec cache mémoire.
        
        Args:
            client_id: Client ID OAuth2
            client_secret: Client Secret OAuth2
            token_url: URL d'obtention du token
            scope: Scope optionnel (ex: "read write")
            token_expiry_margin: Secondes avant expiration pour refresh (défaut: 60s)
        
        Examples:
            >>> auth = OAuth2InMemoryAuth(
            ...     client_id="my_client",
            ...     client_secret="secret123",
            ...     token_url="https://api.example.com/oauth/token"
            ... )
        """
        self._client_id = client_id
        self._client_secret = client_secret
        self._token_url = token_url
        self._scope = scope
        self._token_expiry_margin = token_expiry_margin
        
        # Cache en mémoire
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[float] = None  # timestamp Unix
    
    def get_headers(self) -> Dict[str, str]:
        """
        Retourne Authorization header avec token OAuth2.
        
        Refresh automatique si token expiré ou proche expiration.
        
        Returns:
            Dict avec Authorization: Bearer <token>
        
        Raises:
            AuthenticationError: Si impossible d'obtenir token.
        """
        if self._is_token_expired():
            self._refresh_token()
        
        if self._access_token is None:
            raise AuthenticationError("No access token available")
        
        return {"Authorization": f"Bearer {self._access_token}"}
    
    def on_auth_failure(self, status_code: int, response_body: Optional[str] = None) -> None:
        """
        Invalide le cache si erreur 401.
        
        Force un nouveau token au prochain get_headers().
        """
        if status_code == 401:
            self._access_token = None
            self._token_expires_at = None
    
    def validate(self) -> None:
        """
        Valide la configuration OAuth2.
        
        Raises:
            ValueError: Si paramètres manquants ou invalides.
        """
        if not self._client_id:
            raise ValueError("OAuth2: client_id is required")
        if not self._client_secret:
            raise ValueError("OAuth2: client_secret is required")
        if not self._token_url:
            raise ValueError("OAuth2: token_url is required")
        
        # Valider que token_url est une URL valide
        if not self._token_url.startswith(("http://", "https://")):
            raise ValueError(f"OAuth2: token_url must be http/https URL, got: {self._token_url}")
    
    def _is_token_expired(self) -> bool:
        """
        Vérifie si le token est expiré ou proche de l'expiration.
        
        Returns:
            True si token absent, expiré, ou expire dans moins de token_expiry_margin secondes.
        """
        if self._access_token is None or self._token_expires_at is None:
            return True
        
        # Expirer avec marge de sécurité (défaut 60s avant expiration réelle)
        now = time.time()
        return now >= (self._token_expires_at - self._token_expiry_margin)
    
    def _refresh_token(self) -> None:
        """
        Obtient un nouveau token via OAuth2 Client Credentials flow.
        
        Raises:
            AuthenticationError: Si requête échoue ou réponse invalide.
        """
        payload = {
            "grant_type": "client_credentials",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }
        
        if self._scope:
            payload["scope"] = self._scope
        
        try:
            response = requests.post(
                self._token_url,
                data=payload,
                timeout=30,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            response.raise_for_status()
            
        except requests.exceptions.RequestException as e:
            raise AuthenticationError(
                f"OAuth2: Failed to obtain token from {self._token_url}: {e}"
            ) from e
        
        try:
            token_data = response.json()
        except Exception as e:
            raise AuthenticationError(
                f"OAuth2: Invalid JSON response from token endpoint: {e}"
            ) from e
        
        # Parser réponse OAuth2 standard
        access_token = token_data.get("access_token")
        if not access_token:
            raise AuthenticationError(
                f"OAuth2: Response missing 'access_token' field. Response: {token_data}"
            )
        
        # Calculer expiration (défaut 3600s si non fourni)
        expires_in = token_data.get("expires_in", 3600)
        if not isinstance(expires_in, (int, float)):
            expires_in = 3600
        
        # Stocker dans cache mémoire
        self._access_token = access_token
        self._token_expires_at = time.time() + float(expires_in)
