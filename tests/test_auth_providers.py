

import pytest
import time
from unittest.mock import Mock, patch, MagicMock
import requests_mock
import requests

import sys
sys.path.insert(0, '/home/claude/web_api_connector_mvp')

from plugins.auth_providers import AuthenticationError, APIKeyAuth, BearerTokenAuth, OAuth2InMemoryAuth


# ============================================================
# Tests APIKeyAuth
# ============================================================

def test_api_key_auth_standard():
    """Test: API key avec header standard X-API-Key."""
    auth = APIKeyAuth(key="secret123")
    
    headers = auth.get_headers()
    
    assert headers == {"X-API-Key": "secret123"}


def test_api_key_auth_custom_header():
    """Test: API key avec header custom."""
    auth = APIKeyAuth(key="mykey", header_name="API-Token")
    
    headers = auth.get_headers()
    
    assert headers == {"API-Token": "mykey"}


def test_api_key_auth_with_prefix():
    """Test: API key avec préfixe (ex: Authorization: ApiKey xxx)."""
    auth = APIKeyAuth(
        key="abc123",
        header_name="Authorization",
        prefix="ApiKey "
    )
    
    headers = auth.get_headers()
    
    assert headers == {"Authorization": "ApiKey abc123"}


def test_api_key_auth_validation_empty_key():
    """Test: Validation échoue si clé vide."""
    auth = APIKeyAuth(key="")
    
    with pytest.raises(ValueError, match="API key must be"):
        auth.validate()


def test_api_key_auth_validation_empty_header():
    """Test: Validation échoue si header_name vide."""
    auth = APIKeyAuth(key="valid", header_name="")
    
    with pytest.raises(ValueError, match="Header name must be"):
        auth.validate()


# ============================================================
# Tests BearerTokenAuth
# ============================================================

def test_bearer_token_auth_standard():
    """Test: Bearer token génère Authorization header."""
    auth = BearerTokenAuth(token="abc123xyz")
    
    headers = auth.get_headers()
    
    assert headers == {"Authorization": "Bearer abc123xyz"}


def test_bearer_token_validation_empty():
    """Test: Validation échoue si token vide."""
    auth = BearerTokenAuth(token="")
    
    with pytest.raises(ValueError, match="Bearer token must be"):
        auth.validate()


# ============================================================
# Tests OAuth2InMemoryAuth
# ============================================================

def test_oauth2_validation_missing_client_id():
    """Test: Validation échoue si client_id manquant."""
    auth = OAuth2InMemoryAuth(
        client_id="",
        client_secret="secret",
        token_url="https://api.example.com/token"
    )
    
    with pytest.raises(ValueError, match="client_id is required"):
        auth.validate()


def test_oauth2_validation_missing_client_secret():
    """Test: Validation échoue si client_secret manquant."""
    auth = OAuth2InMemoryAuth(
        client_id="client",
        client_secret="",
        token_url="https://api.example.com/token"
    )
    
    with pytest.raises(ValueError, match="client_secret is required"):
        auth.validate()


def test_oauth2_validation_invalid_token_url():
    """Test: Validation échoue si token_url invalide."""
    auth = OAuth2InMemoryAuth(
        client_id="client",
        client_secret="secret",
        token_url="not-a-url"
    )
    
    with pytest.raises(ValueError, match="token_url must be http"):
        auth.validate()


def test_oauth2_get_token_success():
    """Test: OAuth2 obtient token et le met en cache."""
    with requests_mock.Mocker() as m:
        # Mock endpoint token
        m.post(
            "https://api.example.com/token",
            json={
                "access_token": "token_abc123",
                "expires_in": 3600,
                "token_type": "Bearer"
            }
        )
        
        auth = OAuth2InMemoryAuth(
            client_id="client",
            client_secret="secret",
            token_url="https://api.example.com/token"
        )
        
        # Premier appel: doit fetcher token
        headers = auth.get_headers()
        
        assert headers == {"Authorization": "Bearer token_abc123"}
        assert m.call_count == 1
        
        # Deuxième appel: doit utiliser cache (pas de nouvelle requête)
        headers2 = auth.get_headers()
        
        assert headers2 == {"Authorization": "Bearer token_abc123"}
        assert m.call_count == 1  # Toujours 1 = cache utilisé


def test_oauth2_refresh_on_expiration():
    """Test: OAuth2 refresh automatique quand token expire."""
    with requests_mock.Mocker() as m:
        # Premier token (expire dans 1 seconde)
        m.post(
            "https://api.example.com/token",
            json={
                "access_token": "token_1",
                "expires_in": 1  # Expire dans 1 seconde
            }
        )
        
        auth = OAuth2InMemoryAuth(
            client_id="client",
            client_secret="secret",
            token_url="https://api.example.com/token",
            token_expiry_margin=0  # Pas de marge pour test
        )
        
        # Premier appel
        headers1 = auth.get_headers()
        assert headers1 == {"Authorization": "Bearer token_1"}
        assert m.call_count == 1
        
        # Attendre expiration
        time.sleep(1.1)
        
        # Mock deuxième token
        m.post(
            "https://api.example.com/token",
            json={
                "access_token": "token_2",
                "expires_in": 3600
            }
        )
        
        # Deuxième appel: doit refresh
        headers2 = auth.get_headers()
        assert headers2 == {"Authorization": "Bearer token_2"}
        assert m.call_count == 2  # Nouvelle requête


def test_oauth2_on_auth_failure_invalidates_cache():
    """Test: on_auth_failure() invalide le cache."""
    with requests_mock.Mocker() as m:
        m.post(
            "https://api.example.com/token",
            json={"access_token": "token_abc", "expires_in": 3600}
        )
        
        auth = OAuth2InMemoryAuth(
            client_id="client",
            client_secret="secret",
            token_url="https://api.example.com/token"
        )
        
        # Obtenir token initial
        auth.get_headers()
        assert m.call_count == 1
        
        # Simuler erreur 401
        auth.on_auth_failure(status_code=401)
        
        # Prochain appel doit refetcher token
        m.post(
            "https://api.example.com/token",
            json={"access_token": "token_new", "expires_in": 3600}
        )
        
        headers = auth.get_headers()
        assert headers == {"Authorization": "Bearer token_new"}
        assert m.call_count == 2  # Nouveau token fetchés


def test_oauth2_with_scope():
    """Test: OAuth2 envoie scope dans requête token."""
    with requests_mock.Mocker() as m:
        m.post(
            "https://api.example.com/token",
            json={"access_token": "token", "expires_in": 3600}
        )
        
        auth = OAuth2InMemoryAuth(
            client_id="client",
            client_secret="secret",
            token_url="https://api.example.com/token",
            scope="read write"
        )
        
        auth.get_headers()
        
        # Vérifier que scope est envoyé
        request = m.last_request
        assert "scope=read+write" in request.text or "scope=read%20write" in request.text


def test_oauth2_missing_access_token_in_response():
    """Test: Erreur si réponse ne contient pas access_token."""
    with requests_mock.Mocker() as m:
        # Réponse invalide (manque access_token)
        m.post(
            "https://api.example.com/token",
            json={"token_type": "Bearer", "expires_in": 3600}
        )
        
        auth = OAuth2InMemoryAuth(
            client_id="client",
            client_secret="secret",
            token_url="https://api.example.com/token"
        )
        
        with pytest.raises(AuthenticationError, match="missing 'access_token'"):
            auth.get_headers()


def test_oauth2_network_error():
    """Test: Erreur réseau lève AuthenticationError."""
    with requests_mock.Mocker() as m:
        # Simuler erreur réseau
        m.post(
            "https://api.example.com/token",
            exc=requests.exceptions.ConnectionError("Network error")
        )
        
        auth = OAuth2InMemoryAuth(
            client_id="client",
            client_secret="secret",
            token_url="https://api.example.com/token"
        )
        
        with pytest.raises(AuthenticationError, match="Failed to obtain token"):
            auth.get_headers()


# ============================================================
# Résumé Tests Auth
# ============================================================

"""
Tests Auth Providers - 16 tests

APIKeyAuth: 5 tests
- Headers standard et custom
- Validation key/header_name

BearerTokenAuth: 2 tests
- Format Bearer
- Validation token

OAuth2InMemoryAuth: 9 tests
- Token fetch et cache
- Refresh sur expiration
- Invalidation sur 401
- Scope support
- Error handling (missing token, network error)

Coverage: 100% des fonctionnalités MVP
"""

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
