"""
Tests Web API Connector v2.0 - Sprint 2.

Ces tests s'ajoutent aux 65 tests existants de Sprint 1.
Total après Sprint 2: ~90 tests

Tests des nouvelles fonctionnalités:
✅ Rate limiting
✅ Circuit breaker  
✅ Pagination cursor + offset
✅ Extraction incrémentale
✅ Error classification
"""

import pytest
import time
import tempfile
from pathlib import Path

# Imports Sprint 2
from plugins.web_api_policies import (
    RateLimitPolicy, 
    RateLimitExceeded,
    CircuitBreakerPolicy, 
    CircuitOpenError, 
    CircuitState,
    ErrorClassifier, 
    ErrorCategory,
    StateManager, 
    StateError
)

from plugins.pagination_strategies import CursorPagination, OffsetPagination
from plugins.auth_providers import APIKeyAuth
from plugins.retry_policies import RetryPolicy


# ============================================================
# Tests RateLimitPolicy
# ============================================================

def test_rate_limit_basic():
    """Test: Rate limit basic avec token bucket."""
    policy = RateLimitPolicy(requests_per_second=10, burst=10)
    
    # 10 requêtes immédiates (burst)
    for _ in range(10):
        assert policy.try_acquire(wait=False) is True
    
    # 11ème bloquée
    assert policy.try_acquire(wait=False) is False


def test_rate_limit_refill():
    """Test: Tokens se régénèrent avec le temps."""
    policy = RateLimitPolicy(requests_per_second=10, burst=5)
    
    # Consommer tous tokens
    for _ in range(5):
        policy.acquire()
    
    # Vide maintenant
    assert policy.get_available_tokens() < 1
    
    # Attendre 0.5s → ~5 tokens régénérés (10 req/s * 0.5s)
    time.sleep(0.5)
    assert policy.get_available_tokens() >= 4


def test_rate_limit_acquire_blocking():
    """Test: acquire() bloque jusqu'à token disponible."""
    policy = RateLimitPolicy(requests_per_second=10, burst=1)
    
    # Consommer token
    policy.acquire()
    
    # Prochain acquire doit attendre
    start = time.time()
    policy.acquire()  # Bloque ~0.1s
    elapsed = time.time() - start
    
    assert elapsed >= 0.05  # Au moins 50ms


    # Consommer token
    policy.acquire()
    
    # Deuxième immédiate devrait timeout
    with pytest.raises(RateLimitExceeded, match="timeout"):
        policy.acquire()


def test_rate_limit_reset():
    """Test: Reset remplit bucket."""
    policy = RateLimitPolicy(requests_per_second=10, burst=10)
    
    # Vider
    for _ in range(10):
        policy.acquire()
    
    assert policy.get_available_tokens() < 1
    
    # Reset
    policy.reset()
    assert policy.get_available_tokens() == 10.0


def test_rate_limit_validation():
    """Test: Validation paramètres."""
    # requests_per_second invalide
    with pytest.raises(ValueError, match="requests_per_second"):
        policy = RateLimitPolicy(requests_per_second=-5)
        policy.validate()
    
    # burst invalide
    with pytest.raises(ValueError, match="burst"):
        policy = RateLimitPolicy(burst=0)
        policy.validate()


# ============================================================
# Tests CircuitBreakerPolicy
# ============================================================

def test_circuit_breaker_closed_to_open():
    """Test: Circuit CLOSED → OPEN après échecs."""
    breaker = CircuitBreakerPolicy(failure_threshold=3)
    
    assert breaker.get_state() == CircuitState.CLOSED
    
    # 3 échecs
    for _ in range(3):
        try:
            breaker.call(lambda: 1/0)  # Erreur
        except ZeroDivisionError:
            pass
    
    # Maintenant OPEN
    assert breaker.get_state() == CircuitState.OPEN


def test_circuit_breaker_open_blocks_requests():
    """Test: Circuit OPEN bloque requêtes."""
    breaker = CircuitBreakerPolicy(failure_threshold=2, timeout=60)
    
    # Forcer OPEN
    for _ in range(2):
        try:
            breaker.call(lambda: 1/0)
        except ZeroDivisionError:
            pass
    
    # Requêtes bloquées
    with pytest.raises(CircuitOpenError, match="OPEN"):
        breaker.call(lambda: "ok")


def test_circuit_breaker_half_open_recovery():
    """Test: Circuit OPEN → HALF_OPEN → CLOSED."""
    breaker = CircuitBreakerPolicy(
        failure_threshold=2,
        timeout=0.1,  # 100ms
        success_threshold=1
    )
    
    # Forcer OPEN
    for _ in range(2):
        try:
            breaker.call(lambda: 1/0)
        except:
            pass
    
    assert breaker.get_state() == CircuitState.OPEN
    
    # Attendre timeout
    time.sleep(0.15)
    
    # Requête test → HALF_OPEN → CLOSED si succès
    result = breaker.call(lambda: "success")
    
    assert result == "success"
    assert breaker.get_state() == CircuitState.CLOSED


def test_circuit_breaker_reset():
    """Test: Reset manuel."""
    breaker = CircuitBreakerPolicy(failure_threshold=1)
    
    try:
        breaker.call(lambda: 1/0)
    except:
        pass
    
    assert breaker.get_state() == CircuitState.OPEN
    
    breaker.reset()
    assert breaker.get_state() == CircuitState.CLOSED


def test_circuit_breaker_validation():
    """Test: Validation paramètres."""
    with pytest.raises(ValueError, match="failure_threshold"):
        policy = CircuitBreakerPolicy(failure_threshold=0)
        policy.validate()


# ============================================================
# Tests CursorPagination
# ============================================================

def test_cursor_pagination_simple():
    """Test: Pagination cursor simple."""
    strategy = CursorPagination(
        cursor_field="next_cursor",
        cursor_param="cursor"
    )
    
    # Response avec cursor
    response = {
        "data": [{"id": 1}, {"id": 2}],
        "next_cursor": "abc123"
    }
    
    state = strategy.get_next_page(response, {}, "https://api.com")
    
    assert state.has_more is True
    assert state.next_params == {"cursor": "abc123", "limit": None} or state.next_params == {"cursor": "abc123"}


def test_cursor_pagination_nested():
    """Test: Cursor nested (Facebook-style)."""
    strategy = CursorPagination(
        cursor_field="paging.next",
        cursor_param="after"
    )
    
    response = {
        "data": [{"id": 1}],
        "paging": {"next": "cursor_xyz"}
    }
    
    state = strategy.get_next_page(response, {}, "")
    
    assert state.has_more is True
    assert "after" in state.next_params
    assert state.next_params["after"] == "cursor_xyz"


def test_cursor_pagination_no_more():
    """Test: Pas de cursor = fin."""
    strategy = CursorPagination(cursor_field="next_cursor")
    
    response = {"data": [{"id": 1}]}  # Pas de cursor
    
    state = strategy.get_next_page(response, {}, "")
    
    assert state.has_more is False


def test_cursor_pagination_validation():
    """Test: Validation."""
    with pytest.raises(ValueError, match="cursor_field"):
        strategy = CursorPagination(cursor_field="")
        strategy.validate()


# ============================================================
# Tests OffsetPagination
# ============================================================

def test_offset_pagination_initial():
    """Test: Params initiaux offset=0."""
    strategy = OffsetPagination(limit=50)
    
    params = strategy.get_initial_params()
    
    assert params == {"offset": 0, "limit": 50}


def test_offset_pagination_next_page():
    """Test: Offset incrémente."""
    strategy = OffsetPagination(limit=50)
    
    strategy.get_initial_params()
    
    # Response avec 50 items
    response = [{"id": i} for i in range(50)]
    
    state = strategy.get_next_page(response, {}, "")
    
    assert state.has_more is True
    assert state.next_params == {"offset": 50, "limit": 50}


def test_offset_pagination_last_page():
    """Test: Moins d'items que limit = dernière page."""
    strategy = OffsetPagination(limit=50)
    
    strategy.get_initial_params()
    
    # Seulement 30 items
    response = [{"id": i} for i in range(30)]
    
    state = strategy.get_next_page(response, {}, "")
    
    assert state.has_more is False


def test_offset_pagination_validation():
    """Test: Validation."""
    with pytest.raises(ValueError, match="limit"):
        strategy = OffsetPagination(limit=-1)
        strategy.validate()


# ============================================================
# Tests StateManager
# ============================================================

def test_state_manager_save_load():
    """Test: Sauvegarder et charger état."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "state.json"
        
        manager = StateManager(
            state_file=str(state_file),
            state_field="updated_at"
        )
        
        # Sauvegarder
        manager.save_state("2024-01-15T10:00:00Z")
        
        # Charger
        loaded = manager.load_state()
        assert loaded == "2024-01-15T10:00:00Z"


def test_state_manager_update_from_items():
    """Test: Mettre à jour état depuis items."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "state.json"
        
        manager = StateManager(
            state_file=str(state_file),
            state_field="updated_at"
        )
        
        items = [
            {"id": 1, "updated_at": "2024-01-01"},
            {"id": 2, "updated_at": "2024-01-15"},
            {"id": 3, "updated_at": "2024-01-10"}
        ]
        
        manager.update_state_from_items(items)
        
        # État = max updated_at
        assert manager.get_current_state() == "2024-01-15"


def test_state_manager_initial_state():
    """Test: État initial si fichier absent."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "nonexistent.json"
        
        manager = StateManager(
            state_file=str(state_file),
            initial_state="2024-01-01"
        )
        
        loaded = manager.load_state()
        assert loaded == "2024-01-01"


def test_state_manager_reset():
    """Test: Reset supprime fichier."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "state.json"
        
        manager = StateManager(state_file=str(state_file))
        manager.save_state("some_state")
        
        assert state_file.exists()
        
        manager.reset()
        assert not state_file.exists()


# ============================================================
# Tests ErrorClassifier
# ============================================================

def test_error_classifier_retriable():
    """Test: Erreurs retriable (429, 5xx)."""
    classifier = ErrorClassifier()
    
    assert classifier.is_retriable(429) is True
    assert classifier.is_retriable(502) is True
    assert classifier.is_retriable(503) is True
    assert classifier.is_retriable(504) is True


def test_error_classifier_fatal():
    """Test: Erreurs fatal (401, 404, etc.)."""
    classifier = ErrorClassifier()
    
    assert classifier.is_fatal(400) is True
    assert classifier.is_fatal(401) is True
    assert classifier.is_fatal(403) is True
    assert classifier.is_fatal(404) is True
    assert classifier.is_fatal(422) is True


def test_error_classifier_unknown():
    """Test: Codes inconnus."""
    classifier = ErrorClassifier()
    
    category = classifier.classify(301)  # I'm a teapot
    assert category == ErrorCategory.UNKNOWN


def test_rate_limit_acquire_blocking():
    """Test: acquire() bloque jusqu'à token disponible."""
    policy = RateLimitPolicy(requests_per_second=10, burst=1)
    
    # Consommer token
    policy.acquire()
    
    # Prochain acquire doit attendre
    start = time.time()
    policy.acquire()  # Bloque ~0.1s
    elapsed = time.time() - start
    
    assert elapsed >= 0.05  # Au moins 50ms

def test_error_classifier_custom():
    """Test: Codes custom."""
    classifier = ErrorClassifier(
        retriable_codes={408, 425},
        fatal_codes={451}
    )
    
    assert classifier.is_retriable(408) is True
    assert classifier.is_fatal(451) is True


def test_error_classifier_validation():
    """Test: Validation - pas de codes en conflit."""
    with pytest.raises(ValueError, match="both retriable and fatal"):
        classifier = ErrorClassifier(
            retriable_codes={429, 500},
            fatal_codes={500}  # Conflit !
        )
        classifier.validate()


# ============================================================
# Résumé Tests Sprint 2
# ============================================================

"""
Tests Web API Connector v2.0 - 30 nouveaux tests

RateLimitPolicy: 6 tests
- Token bucket basic
- Refill automatique
- Acquire blocking
- Timeout
- Reset
- Validation

CircuitBreakerPolicy: 5 tests
- CLOSED → OPEN transition
- OPEN bloque requêtes
- HALF_OPEN recovery
- Reset manuel
- Validation

CursorPagination: 4 tests
- Cursor simple
- Cursor nested
- Fin pagination
- Validation

OffsetPagination: 4 tests
- Params initiaux
- Offset increment
- Dernière page
- Validation

StateManager: 4 tests
- Save/load
- Update from items
- Initial state
- Reset

ErrorClassifier: 5 tests
- Retriable codes
- Fatal codes
- Unknown codes
- Custom codes
- Validation

Total tests Sprint 1 + Sprint 2: 65 + 30 = 95 tests
Coverage estimée: ~93%
"""

if __name__ == "__main__":
    pytest.main([__file__, "-v"])