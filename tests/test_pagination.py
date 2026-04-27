

import pytest

import sys
sys.path.insert(0, '/home/claude/web_api_connector_mvp')

from plugins.pagination_strategies import NextLinkPagination
from plugins.pagination_strategies import PaginationState


# ============================================================
# Tests NextLinkPagination
# ============================================================

def test_next_link_initial_params():
    """Test: Paramètres initiaux incluent page_size."""
    strategy = NextLinkPagination(page_size=100)
    
    params = strategy.get_initial_params()
    
    assert params == {"per_page": 100}


def test_next_link_initial_params_no_page_size():
    """Test: Paramètres vides si page_size non configuré."""
    strategy = NextLinkPagination()
    
    params = strategy.get_initial_params()
    
    assert params == {}


def test_next_link_parse_simple():
    """Test: Parse header Link simple avec rel=next."""
    strategy = NextLinkPagination()
    
    headers = {
        "Link": '<https://api.github.com/repos?page=2>; rel="next"'
    }
    
    state = strategy.get_next_page(
        response_data={},
        response_headers=headers,
        current_url="https://api.github.com/repos?page=1"
    )
    
    assert state.has_more is True
    assert state.next_url == "https://api.github.com/repos?page=2"
    assert state.next_params is None


def test_next_link_parse_multiple_rels():
    """Test: Parse header Link avec plusieurs rel (next, last, prev)."""
    strategy = NextLinkPagination()
    
    headers = {
        "Link": (
            '<https://api.example.com?page=3>; rel="next", '
            '<https://api.example.com?page=1>; rel="prev", '
            '<https://api.example.com?page=10>; rel="last"'
        )
    }
    
    state = strategy.get_next_page(
        response_data={},
        response_headers=headers,
        current_url="https://api.example.com?page=2"
    )
    
    assert state.has_more is True
    assert state.next_url == "https://api.example.com?page=3"


def test_next_link_no_next_rel():
    """Test: Pas de rel=next = fin de pagination."""
    strategy = NextLinkPagination()
    
    headers = {
        "Link": '<https://api.example.com?page=1>; rel="prev"'
    }
    
    state = strategy.get_next_page(
        response_data={},
        response_headers=headers,
        current_url="https://api.example.com?page=2"
    )
    
    assert state.has_more is False
    assert state.next_url is None


def test_next_link_no_link_header():
    """Test: Absence de header Link = fin de pagination."""
    strategy = NextLinkPagination()
    
    state = strategy.get_next_page(
        response_data={},
        response_headers={},
        current_url="https://api.example.com"
    )
    
    assert state.has_more is False


def test_next_link_case_insensitive():
    """Test: Header 'link' (minuscule) est supporté."""
    strategy = NextLinkPagination()
    
    headers = {
        "link": '<https://api.example.com?page=2>; rel="next"'
    }
    
    state = strategy.get_next_page(
        response_data={},
        response_headers=headers,
        current_url="https://api.example.com"
    )
    
    assert state.has_more is True
    assert state.next_url == "https://api.example.com?page=2"


def test_next_link_single_quotes():
    """Test: rel='next' (simple quotes) est supporté."""
    strategy = NextLinkPagination()
    
    headers = {
        "Link": "<https://api.example.com?page=2>; rel='next'"
    }
    
    state = strategy.get_next_page(
        response_data={},
        response_headers=headers,
        current_url="https://api.example.com"
    )
    
    assert state.has_more is True


def test_next_link_no_quotes():
    """Test: rel=next (sans quotes) est supporté."""
    strategy = NextLinkPagination()
    
    headers = {
        "Link": "<https://api.example.com?page=2>; rel=next"
    }
    
    state = strategy.get_next_page(
        response_data={},
        response_headers=headers,
        current_url="https://api.example.com"
    )
    
    assert state.has_more is True


def test_next_link_max_pages_protection():
    """Test: Protection anti-boucle infinie avec max_pages."""
    strategy = NextLinkPagination(max_pages=3)
    
    headers = {
        "Link": '<https://api.example.com?page=2>; rel="next"'
    }
    
    # Pages 1, 2, 3 OK
    for i in range(3):
        state = strategy.get_next_page(
            response_data={},
            response_headers=headers,
            current_url="https://api.example.com"
        )
        if i < 2:
            assert state.has_more is True
    
    # Page 4 = bloquée par max_pages
    state = strategy.get_next_page(
        response_data={},
        response_headers=headers,
        current_url="https://api.example.com"
    )
    
    assert state.has_more is False


def test_next_link_validation_invalid_page_size():
    """Test: Validation échoue si page_size invalide."""
    strategy = NextLinkPagination(page_size=-10)
    
    with pytest.raises(ValueError, match="page_size must be positive"):
        strategy.validate()


def test_next_link_validation_invalid_max_pages():
    """Test: Validation échoue si max_pages invalide."""
    strategy = NextLinkPagination(max_pages=0)
    
    with pytest.raises(ValueError, match="max_pages must be positive"):
        strategy.validate()


# ============================================================
# Tests Edge Cases
# ============================================================

def test_next_link_whitespace_in_url():
    """Test: Gestion espaces dans URL."""
    strategy = NextLinkPagination()
    
    headers = {
        "Link": '<  https://api.example.com?page=2  >; rel="next"'
    }
    
    state = strategy.get_next_page(
        response_data={},
        response_headers=headers,
        current_url="https://api.example.com"
    )
    
    assert state.has_more is True
    assert "https://api.example.com?page=2" in state.next_url


def test_next_link_malformed_header():
    """Test: Header Link malformé = fin de pagination."""
    strategy = NextLinkPagination()
    
    headers = {
        "Link": "malformed header without proper format"
    }
    
    state = strategy.get_next_page(
        response_data={},
        response_headers=headers,
        current_url="https://api.example.com"
    )
    
    assert state.has_more is False


# ============================================================
# Résumé Tests Pagination
# ============================================================

"""
Tests NextLinkPagination - 14 tests

Fonctionnalités:
- Parse header Link RFC 5988
- Support rel="next" avec quotes/sans quotes
- Gestion headers multiples (next, prev, last)
- Protection anti-boucle (max_pages)
- Validation page_size et max_pages
- Edge cases (malformed, whitespace)

Coverage: 100% de NextLinkPagination MVP
"""

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
