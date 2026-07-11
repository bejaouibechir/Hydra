"""
Test MongoDB connector integration with registry.

Run with: pytest tests/test_mongodb_registry.py -v
"""

import pytest
from internal.connector.registry import build_connector, CONNECTOR_REGISTRY
try:
    from plugins.connectors.mongodb import MongoDBConnector
    _MONGO_AVAILABLE = True
except Exception:
    MongoDBConnector = None  # type: ignore
    _MONGO_AVAILABLE = False


# ============================================================
# Tests Registry MongoDB
# ============================================================

@pytest.mark.skipif(not _MONGO_AVAILABLE, reason="pymongo non disponible")
def test_registry_has_mongodb():
    """Verify MongoDB is registered."""
    assert "mongodb" in CONNECTOR_REGISTRY
    assert callable(CONNECTOR_REGISTRY["mongodb"])


@pytest.mark.skipif(not _MONGO_AVAILABLE, reason="pymongo non disponible")
def test_build_mongodb_connector():
    """Test building MongoDB connector via registry."""
    config = {
        "type": "mongodb",
        "connection": {
            "uri": "mongodb://localhost:27017",
            "database": "test_db"
        },
        "extract": {
            "collection": "test_collection"
        }
    }
    
    connector = build_connector(name="test_mongo", config=config)
    
    assert connector is not None
    assert connector.name == "test_mongo"
    assert isinstance(connector, MongoDBConnector)


@pytest.mark.skipif(not _MONGO_AVAILABLE, reason="pymongo non disponible")
def test_mongodb_connector_standard_signature():
    """MongoDB uses standard (name, config) signature."""
    config = {
        "type": "mongodb",
        "connection": {
            "uri": "mongodb://localhost:27017",
            "database": "test_db"
        },
        "extract": {
            "collection": "users"
        }
    }
    
    connector = build_connector(name="mongo_src", config=config)
    
    assert connector.name == "mongo_src"
    assert isinstance(connector, MongoDBConnector)


@pytest.mark.skipif(not _MONGO_AVAILABLE, reason="pymongo non disponible")
def test_mongodb_connector_missing_database():
    """MongoDB connector requires database name."""
    config = {
        "type": "mongodb",
        "connection": {
            "uri": "mongodb://localhost:27017"
            # Missing: database
        },
        "extract": {
            "collection": "users"
        }
    }
    
    with pytest.raises(ValueError) as exc:
        build_connector(name="test_mongo", config=config)
    
    assert "database" in str(exc.value).lower()


@pytest.mark.skipif(not _MONGO_AVAILABLE, reason="pymongo non disponible")
def test_mongodb_connector_missing_collection():
    """MongoDB connector requires collection name."""
    config = {
        "type": "mongodb",
        "connection": {
            "uri": "mongodb://localhost:27017",
            "database": "test_db"
        },
        "extract": {
            # Missing: collection
        }
    }
    
    with pytest.raises(ValueError) as exc:
        build_connector(name="test_mongo", config=config)
    
    assert "collection" in str(exc.value).lower()


@pytest.mark.skipif(not _MONGO_AVAILABLE, reason="pymongo non disponible")
def test_mongodb_case_insensitive():
    """MongoDB type is case-insensitive."""
    config = {
        "type": "MongoDB",  # Mixed case
        "connection": {
            "uri": "mongodb://localhost:27017",
            "database": "test_db"
        },
        "extract": {
            "collection": "users"
        }
    }
    
    connector = build_connector(name="test", config=config)
    assert isinstance(connector, MongoDBConnector)


# ============================================================
# Extensibility Tests
# ============================================================

@pytest.mark.skipif(not _MONGO_AVAILABLE, reason="pymongo non disponible")
def test_registry_extensibility_mongodb():
    """
    Validate that adding MongoDB required only:
    - +1 import line
    - +1 registry line
    
    No changes to build_connector() or dispatch logic.
    """
    # Check registry contains MongoDB
    assert "mongodb" in CONNECTOR_REGISTRY
    
    # Check it's a proper factory
    factory = CONNECTOR_REGISTRY["mongodb"]
    assert callable(factory)
    
    # Verify factory works
    config = {
        "type": "mongodb",
        "connection": {"uri": "mongodb://localhost", "database": "db"},
        "extract": {"collection": "col"}
    }
    
    connector = factory("test", config)
    assert isinstance(connector, MongoDBConnector)


@pytest.mark.skipif(not _MONGO_AVAILABLE, reason="pymongo non disponible")
def test_all_connector_types():
    """Verify all registered connector types."""
    expected_types = ["csv", "mysql", "mariadb", "mongodb"]
    
    for ctype in expected_types:
        assert ctype in CONNECTOR_REGISTRY, f"Missing connector type: {ctype}"


# ============================================================
# Summary
# ============================================================

"""
Tests validate:
✅ MongoDB registered in CONNECTOR_REGISTRY
✅ Uses standard factory pattern
✅ Proper validation (database, collection required)
✅ Case-insensitive type matching
✅ Extensibility maintained (+2 lines = new connector)
"""

if __name__ == "__main__":
    pytest.main([__file__, "-v"])