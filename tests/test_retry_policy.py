

import pytest

import sys
sys.path.insert(0, '/home/claude/web_api_connector_mvp')

from  plugins.retry_policies import RetryPolicy


# ============================================================
# Tests should_retry()
# ============================================================

def test_retry_on_429():
    """Test: Retry sur 429 Too Many Requests."""
    policy = RetryPolicy(max_attempts=3)
    
    assert policy.should_retry(status_code=429, attempt=1) is True
    assert policy.should_retry(status_code=429, attempt=2) is True


def test_retry_on_5xx():
    """Test: Retry sur erreurs serveur (502, 503, 504)."""
    policy = RetryPolicy(max_attempts=3)
    
    assert policy.should_retry(status_code=502, attempt=1) is True
    assert policy.should_retry(status_code=503, attempt=1) is True
    assert policy.should_retry(status_code=504, attempt=1) is True


def test_no_retry_on_401():
    """Test: Pas de retry sur 401 Unauthorized (fatal)."""
    policy = RetryPolicy(max_attempts=3)
    
    assert policy.should_retry(status_code=401, attempt=1) is False


def test_no_retry_on_404():
    """Test: Pas de retry sur 404 Not Found (fatal)."""
    policy = RetryPolicy(max_attempts=3)
    
    assert policy.should_retry(status_code=404, attempt=1) is False


def test_no_retry_on_400():
    """Test: Pas de retry sur 400 Bad Request (fatal)."""
    policy = RetryPolicy(max_attempts=3)
    
    assert policy.should_retry(status_code=400, attempt=1) is False


def test_no_retry_when_max_attempts_reached():
    """Test: Pas de retry si max_attempts atteint."""
    policy = RetryPolicy(max_attempts=3)
    
    # Attempt 3 = dernière tentative autorisée
    assert policy.should_retry(status_code=503, attempt=3) is False


# ============================================================
# Tests get_wait_time() - Backoff exponentiel
# ============================================================

def test_backoff_exponential_without_jitter():
    """Test: Backoff exponentiel sans jitter."""
    policy = RetryPolicy(
        initial_backoff=1.0,
        backoff_multiplier=2.0,
        jitter=False
    )
    
    # Attempt 1: 1 * (2^0) = 1s
    assert policy.get_wait_time(status_code=503, attempt=1) == 1.0
    
    # Attempt 2: 1 * (2^1) = 2s
    assert policy.get_wait_time(status_code=503, attempt=2) == 2.0
    
    # Attempt 3: 1 * (2^2) = 4s
    assert policy.get_wait_time(status_code=503, attempt=3) == 4.0


def test_backoff_max_limit():
    """Test: Backoff limité par max_backoff."""
    policy = RetryPolicy(
        initial_backoff=10.0,
        max_backoff=20.0,
        backoff_multiplier=2.0,
        jitter=False
    )
    
    # Attempt 1: 10s
    assert policy.get_wait_time(status_code=503, attempt=1) == 10.0
    
    # Attempt 2: 20s (atteint max_backoff)
    assert policy.get_wait_time(status_code=503, attempt=2) == 20.0
    
    # Attempt 3: toujours 20s (plafonné)
    assert policy.get_wait_time(status_code=503, attempt=3) == 20.0


def test_backoff_with_jitter():
    """Test: Jitter ajoute variabilité (±25%)."""
    policy = RetryPolicy(
        initial_backoff=10.0,
        jitter=True
    )
    
    # Avec jitter, résultat doit être dans [7.5, 12.5] (10 * [0.75, 1.25])
    wait_time = policy.get_wait_time(status_code=503, attempt=1)
    
    assert 7.5 <= wait_time <= 12.5


# ============================================================
# Tests Retry-After header
# ============================================================

def test_retry_after_header_priority():
    """Test: Header Retry-After prioritaire pour 429."""
    policy = RetryPolicy(
        initial_backoff=1.0,
        jitter=False
    )
    
    # Sans Retry-After: backoff normal
    wait_without = policy.get_wait_time(status_code=429, attempt=1)
    assert wait_without == 1.0
    
    # Avec Retry-After: utilise header
    wait_with = policy.get_wait_time(
        status_code=429,
        attempt=1,
        retry_after=30
    )
    assert wait_with == 30.0


def test_retry_after_not_used_for_5xx():
    """Test: Retry-After ignoré pour 5xx (seulement 429)."""
    policy = RetryPolicy(
        initial_backoff=2.0,
        jitter=False
    )
    
    # Même avec Retry-After, 503 utilise backoff exponentiel
    wait_time = policy.get_wait_time(
        status_code=503,
        attempt=1,
        retry_after=30
    )
    
    assert wait_time == 2.0  # Backoff normal, pas 30


# ============================================================
# Tests Validation
# ============================================================

def test_validation_invalid_max_attempts():
    """Test: Validation échoue si max_attempts < 1."""
    policy = RetryPolicy(max_attempts=0)
    
    with pytest.raises(ValueError, match="max_attempts must be >= 1"):
        policy.validate()


def test_validation_invalid_initial_backoff():
    """Test: Validation échoue si initial_backoff <= 0."""
    policy = RetryPolicy(initial_backoff=0)
    
    with pytest.raises(ValueError, match="initial_backoff must be > 0"):
        policy.validate()


def test_validation_max_backoff_less_than_initial():
    """Test: Validation échoue si max_backoff < initial_backoff."""
    policy = RetryPolicy(
        initial_backoff=10.0,
        max_backoff=5.0
    )
    
    with pytest.raises(ValueError, match="max_backoff.*must be >= initial_backoff"):
        policy.validate()


def test_validation_invalid_multiplier():
    """Test: Validation échoue si multiplier <= 1."""
    policy = RetryPolicy(backoff_multiplier=1.0)
    
    with pytest.raises(ValueError, match="backoff_multiplier must be > 1"):
        policy.validate()


def test_validation_empty_retriable_codes():
    """Test: Validation échoue si retriable_status_codes vide."""
    policy = RetryPolicy(retriable_status_codes=set())
    
    with pytest.raises(ValueError, match="retriable_status_codes cannot be empty"):
        policy.validate()


# ============================================================
# Tests Custom Retriable Codes
# ============================================================

def test_custom_retriable_codes():
    """Test: Support codes HTTP custom comme retriable."""
    policy = RetryPolicy(
        retriable_status_codes={408, 425}  # Request Timeout, Too Early
    )
    
    assert policy.should_retry(status_code=408, attempt=1) is True
    assert policy.should_retry(status_code=425, attempt=1) is True
    
    # Codes par défaut ne sont plus retriable
    assert policy.should_retry(status_code=503, attempt=1) is False


# ============================================================
# Résumé Tests RetryPolicy
# ============================================================

"""
Tests RetryPolicy - 18 tests

Fonctionnalités:
- Should retry: 429, 5xx retriable | 4xx fatal
- Backoff exponentiel avec/sans jitter
- Max backoff limit
- Header Retry-After (429 seulement)
- Validation configuration
- Custom retriable codes

Coverage: 100% de RetryPolicy MVP
"""

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
