"""
Bearer Token Authentication - Token statique simple.

Cas d'usage:
- APIs avec token Bearer statique
- Tokens longue durée (Personal Access Tokens GitHub, etc.)
"""

from typing import Dict
from .auth_provider import AuthProvider


class BearerTokenAuth(AuthProvider):
    """
    Authentification par Bearer Token statique.
    
    Génère header: Authorization: Bearer <token>
    
    Configuration DSL:
        sources:
          api:
            type: web_api
            auth:
              type: bearer
              token: ${ENV:API_TOKEN}
    """
    
    def __init__(self, token: str):
        """
        Initialise l'authentification Bearer.
        
        Args:
            token: Le token d'accès (sans préfixe "Bearer")
        
        Examples:
            >>> auth = BearerTokenAuth(token="abc123...")
            >>> auth.get_headers()
            {"Authorization": "Bearer abc123..."}
        """
        self._token = token
    
    def get_headers(self) -> Dict[str, str]:
        """
        Retourne le header Authorization avec Bearer token.
        
        Returns:
            Dict avec header Authorization.
        """
        return {"Authorization": f"Bearer {self._token}"}
    
    def validate(self) -> None:
        """
        Valide que le token n'est pas vide.
        
        Raises:
            ValueError: Si token vide.
        """
        if not self._token or not isinstance(self._token, str):
            raise ValueError("Bearer token must be a non-empty string")
