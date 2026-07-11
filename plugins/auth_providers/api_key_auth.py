"""
API Key Authentication - Implémentation simple pour clés API statiques.

Cas d'usage:
- APIs publiques avec clé API (GitHub, OpenWeather, etc.)
- Headers custom (X-API-Key, API-Key, etc.)
"""

from typing import Dict
from .auth_provider import AuthProvider


class APIKeyAuth(AuthProvider):
    """
    Authentification par clé API statique.
    
    Supporte différentes conventions de headers:
    - X-API-Key (défaut)
    - Authorization: ApiKey <key>
    - Custom header name
    
    Configuration DSL:
        sources:
          github_api:
            type: web_api
            auth:
              type: api_key
              key: ${ENV:GITHUB_TOKEN}
              header_name: X-API-Key  # optionnel
    """
    
    def __init__(
        self,
        key: str,
        header_name: str = "X-API-Key",
        prefix: str = ""
    ):
        """
        Initialise l'authentification par clé API.
        
        Args:
            key: La clé API (ex: "ghp_abc123...")
            header_name: Nom du header HTTP (défaut: "X-API-Key")
            prefix: Préfixe optionnel (ex: "ApiKey " pour "Authorization: ApiKey xxx")
        
        Examples:
            >>> # Cas standard
            >>> auth = APIKeyAuth(key="secret123")
            >>> auth.get_headers()
            {"X-API-Key": "secret123"}
            
            >>> # Header custom avec préfixe
            >>> auth = APIKeyAuth(
            ...     key="abc",
            ...     header_name="Authorization",
            ...     prefix="ApiKey "
            ... )
            >>> auth.get_headers()
            {"Authorization": "ApiKey abc"}
        """
        self._key = key
        self._header_name = header_name
        self._prefix = prefix
    
    def get_headers(self) -> Dict[str, str]:
        """
        Retourne le header d'authentification.
        
        Returns:
            Dict avec le header configuré.
        """
        value = f"{self._prefix}{self._key}" if self._prefix else self._key
        return {self._header_name: value}
    
    def validate(self) -> None:
        """
        Valide que la clé API n'est pas vide.
        
        Raises:
            ValueError: Si clé vide.
        """
        if not self._key or not isinstance(self._key, str):
            raise ValueError("API key must be a non-empty string")
        
        if not self._header_name or not isinstance(self._header_name, str):
            raise ValueError("Header name must be a non-empty string")
