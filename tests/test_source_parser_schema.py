"""
Test parser extension pour schema MongoDB.

Run with: pytest tests/test_source_parser_schema.py -v
"""

import pytest
from internal.parser.source import SourceParser, SourcesConfig


# ============================================================
# Tests Schema Config
# ============================================================

def test_parse_source_without_schema():
    """Source sans schema (comportement classique)."""
    yaml_data = {
        "sources": {
            "mysql_src": {
                "type": "mysql",
                "connection": {"host": "localhost"},
                "extract": {"table": "users"}
            }
        }
    }
    
    parser = SourceParser()
    config = parser.parse(yaml_data)
    
    assert "mysql_src" in config.sources
    assert config.sources["mysql_src"].schema is None


def test_parse_mongodb_with_auto_schema():
    """MongoDB avec schema auto (mode simple)."""
    yaml_data = {
        "sources": {
            "mongo_src": {
                "type": "mongodb",
                "connection": {
                    "uri": "mongodb://localhost:27017",
                    "database": "test_db"
                },
                "extract": {
                    "collection": "users"
                },
                "schema": {
                    "mode": "auto"
                }
            }
        }
    }
    
    parser = SourceParser()
    config = parser.parse(yaml_data)
    
    source = config.sources["mongo_src"]
    assert source.type == "mongodb"
    assert source.schema is not None
    assert source.schema.mode == "auto"
    assert source.schema.drift_policy == "warn"  # Default


def test_parse_mongodb_with_manual_schema():
    """MongoDB avec schema manuel complet."""
    yaml_data = {
        "sources": {
            "mongo_orders": {
                "type": "mongodb",
                "connection": {
                    "uri": "mongodb://localhost:27017",
                    "database": "test_db"
                },
                "extract": {
                    "collection": "orders"
                },
                "schema": {
                    "mode": "manual",
                    "fields": [
                        {
                            "name": "order_id",
                            "path": "_id",
                            "type": "string",
                            "required": True
                        },
                        {
                            "name": "customer_name",
                            "path": "customer.name",
                            "type": "string"
                        },
                        {
                            "name": "total",
                            "type": "float",
                            "required": True
                        }
                    ],
                    "drift_policy": "warn",
                    "validation_policy": "best_effort"
                }
            }
        }
    }
    
    parser = SourceParser()
    config = parser.parse(yaml_data)
    
    source = config.sources["mongo_orders"]
    assert source.schema is not None
    assert source.schema.mode == "manual"
    assert len(source.schema.fields) == 3
    
    # Vérifier premier champ
    field1 = source.schema.fields[0]
    assert field1.name == "order_id"
    assert field1.path == "_id"
    assert field1.type == "string"
    assert field1.required is True
    
    # Vérifier champ nested
    field2 = source.schema.fields[1]
    assert field2.name == "customer_name"
    assert field2.path == "customer.name"
    
    # Vérifier policies
    assert source.schema.drift_policy == "warn"
    assert source.schema.validation_policy == "best_effort"


def test_parse_schema_with_array_field():
    """Schema avec champ array."""
    yaml_data = {
        "sources": {
            "mongo_src": {
                "type": "mongodb",
                "connection": {"uri": "mongodb://localhost", "database": "db"},
                "extract": {"collection": "col"},
                "schema": {
                    "mode": "manual",
                    "fields": [
                        {
                            "name": "items",
                            "path": "items",
                            "type": "array",
                            "array_handling": "explode"
                        }
                    ]
                }
            }
        }
    }
    
    parser = SourceParser()
    config = parser.parse(yaml_data)
    
    field = config.sources["mongo_src"].schema.fields[0]
    assert field.name == "items"
    assert field.type == "array"
    assert field.array_handling == "explode"


def test_parse_schema_invalid_mode():
    """Schema avec mode invalide."""
    yaml_data = {
        "sources": {
            "mongo_src": {
                "type": "mongodb",
                "connection": {"uri": "mongodb://localhost", "database": "db"},
                "extract": {"collection": "col"},
                "schema": {
                    "mode": "invalid_mode"
                }
            }
        }
    }
    
    parser = SourceParser()
    
    with pytest.raises(Exception) as exc:
        parser.parse(yaml_data)
    
    assert "mode" in str(exc.value).lower()


def test_parse_schema_invalid_drift_policy():
    """Schema avec drift_policy invalide."""
    yaml_data = {
        "sources": {
            "mongo_src": {
                "type": "mongodb",
                "connection": {"uri": "mongodb://localhost", "database": "db"},
                "extract": {"collection": "col"},
                "schema": {
                    "drift_policy": "invalid_policy"
                }
            }
        }
    }
    
    parser = SourceParser()
    
    with pytest.raises(Exception) as exc:
        parser.parse(yaml_data)
    
    assert "drift_policy" in str(exc.value).lower()


def test_parse_schema_invalid_array_handling():
    """Schema field avec array_handling invalide."""
    yaml_data = {
        "sources": {
            "mongo_src": {
                "type": "mongodb",
                "connection": {"uri": "mongodb://localhost", "database": "db"},
                "extract": {"collection": "col"},
                "schema": {
                    "fields": [
                        {
                            "name": "items",
                            "type": "array",
                            "array_handling": "invalid_handling"
                        }
                    ]
                }
            }
        }
    }
    
    parser = SourceParser()
    
    with pytest.raises(Exception) as exc:
        parser.parse(yaml_data)
    
    assert "array_handling" in str(exc.value).lower()


def test_parse_schema_with_default_value():
    """Schema field avec default value."""
    yaml_data = {
        "sources": {
            "mongo_src": {
                "type": "mongodb",
                "connection": {"uri": "mongodb://localhost", "database": "db"},
                "extract": {"collection": "col"},
                "schema": {
                    "fields": [
                        {
                            "name": "status",
                            "type": "string",
                            "default": "pending"
                        }
                    ]
                }
            }
        }
    }
    
    parser = SourceParser()
    config = parser.parse(yaml_data)
    
    field = config.sources["mongo_src"].schema.fields[0]
    assert field.default == "pending"


def test_parse_mixed_sources():
    """Mix de sources classiques et MongoDB avec schema."""
    yaml_data = {
        "sources": {
            "mysql_src": {
                "type": "mysql",
                "connection": {"host": "localhost"},
                "extract": {"table": "users"}
            },
            "mongo_src": {
                "type": "mongodb",
                "connection": {"uri": "mongodb://localhost", "database": "db"},
                "extract": {"collection": "orders"},
                "schema": {
                    "mode": "infer_strict",
                    "drift_policy": "fail"
                }
            }
        }
    }
    
    parser = SourceParser()
    config = parser.parse(yaml_data)
    
    assert len(config.sources) == 2
    assert config.sources["mysql_src"].schema is None
    assert config.sources["mongo_src"].schema is not None
    assert config.sources["mongo_src"].schema.mode == "infer_strict"


# ============================================================
# Summary
# ============================================================

"""
Tests validate:
✅ Source sans schema (backward compatible)
✅ MongoDB avec schema auto
✅ MongoDB avec schema manuel + fields
✅ Nested fields (path avec dots)
✅ Array fields avec array_handling
✅ Validation des enums (mode, drift_policy, array_handling)
✅ Default values
✅ Mix sources classiques + MongoDB
"""

if __name__ == "__main__":
    pytest.main([__file__, "-v"])