"""Auth Providers package - Strategies d'authentification pour Web API."""

from .auth_provider import AuthProvider, AuthenticationError
from .api_key_auth import APIKeyAuth
from .bearer_token_auth import BearerTokenAuth
from .oauth2_inmemory_auth import OAuth2InMemoryAuth

__all__ = [
    "AuthProvider",
    "AuthenticationError",
    "APIKeyAuth",
    "BearerTokenAuth",
    "OAuth2InMemoryAuth",
]