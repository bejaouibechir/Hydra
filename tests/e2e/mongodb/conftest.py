"""
Conftest for MongoDB E2E tests.

This overrides the parent conftest.py to prevent pg_connection fixture from loading.
"""

import pytest

# Override pg_connection fixture to do nothing
@pytest.fixture(scope="function")
def pg_connection():
    """Dummy fixture to override parent pg_connection."""
    return None