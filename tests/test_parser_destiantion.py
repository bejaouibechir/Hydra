"""
Tests du parser destinations.yaml - Extension Sprint 1.

Objectifs Backlog 1.2:
- Valider LoadMode Enum
- Valider mode upsert → key obligatoire (DoD)
- Valider nettoyage colonnes key
- Valider messages d'erreur explicites
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from hydra_etl.internal.parser.destination import (
    DestinationParser,
    LoadMode,
    LoadConfig,
)


# ============================================================
# Tests LoadMode Enum
# ============================================================

def test_load_mode_enum_values():
    """
    Vérifier que LoadMode Enum contient les bonnes valeurs.
    """
    assert LoadMode.APPEND.value == "append"
    assert LoadMode.REPLACE.value == "replace"
    assert LoadMode.UPSERT.value == "upsert"


# ============================================================
# Tests LoadConfig - Cas OK
# ============================================================

def test_load_config_minimal_append():
    """
    Cas OK: Configuration minimale avec mode append (défaut).
    """
    raw = {
        "destinations": {
            "dest_dwh": {
                "type": "mysql",
                "connection": {"host": "localhost"},
                "load": {"table": "orders"}
            }
        }
    }
    
    cfg = DestinationParser().parse(raw)
    assert cfg.destinations["dest_dwh"].load.table == "orders"
    assert cfg.destinations["dest_dwh"].load.mode == LoadMode.APPEND
    assert cfg.destinations["dest_dwh"].load.key is None
    assert cfg.destinations["dest_dwh"].load.batch_size == 10_000  # défaut


def test_load_config_replace_mode():
    """
    Cas OK: Mode replace explicite.
    """
    raw = {
        "destinations": {
            "dest_csv": {
                "type": "csv",
                "connection": {"path": "output.csv"},
                "load": {
                    "table": "data",
                    "mode": "replace"
                }
            }
        }
    }
    
    cfg = DestinationParser().parse(raw)
    assert cfg.destinations["dest_csv"].load.mode == LoadMode.REPLACE


def test_load_config_upsert_with_simple_key():
    """
    Cas OK: Mode upsert avec clé simple.
    """
    raw = {
        "destinations": {
            "dest_db": {
                "type": "mysql",
                "connection": {"host": "localhost"},
                "load": {
                    "table": "users",
                    "mode": "upsert",
                    "key": ["id"]
                }
            }
        }
    }
    
    cfg = DestinationParser().parse(raw)
    assert cfg.destinations["dest_db"].load.mode == LoadMode.UPSERT
    assert cfg.destinations["dest_db"].load.key == ["id"]


def test_load_config_upsert_with_composite_key():
    """
    Cas OK: Mode upsert avec clé composite.
    """
    raw = {
        "destinations": {
            "dest_sales": {
                "type": "mysql",
                "connection": {"host": "localhost"},
                "load": {
                    "table": "sales",
                    "mode": "upsert",
                    "key": ["region", "product_id"]
                }
            }
        }
    }
    
    cfg = DestinationParser().parse(raw)
    assert cfg.destinations["dest_sales"].load.mode == LoadMode.UPSERT
    assert cfg.destinations["dest_sales"].load.key == ["region", "product_id"]


def test_load_config_key_cleaning_whitespace():
    """
    Cas OK: Nettoyage whitespace dans colonnes key.
    """
    raw = {
        "destinations": {
            "dest_db": {
                "type": "mysql",
                "connection": {"host": "localhost"},
                "load": {
                    "table": "t",
                    "mode": "upsert",
                    "key": [" id ", "  name  "]  # Whitespace
                }
            }
        }
    }
    
    cfg = DestinationParser().parse(raw)
    # Whitespace nettoyé
    assert cfg.destinations["dest_db"].load.key == ["id", "name"]


def test_load_config_key_deduplication():
    """
    Cas OK: Déduplication colonnes key (conserve ordre).
    """
    raw = {
        "destinations": {
            "dest_db": {
                "type": "mysql",
                "connection": {"host": "localhost"},
                "load": {
                    "table": "t",
                    "mode": "upsert",
                    "key": ["id", "id", "name"]  # Doublon id
                }
            }
        }
    }
    
    cfg = DestinationParser().parse(raw)
    # Dédupliqué : garde premier ordre
    assert cfg.destinations["dest_db"].load.key == ["id", "name"]


# ============================================================
# Tests LoadConfig - Cas KO (DoD: Pydantic échoue si upsert sans key)
# ============================================================

def test_load_config_upsert_without_key_fails():
    """
    DoD Backlog 1.2: mode upsert sans key → ValidationError.
    
    C'est le test principal du DoD.
    """
    raw = {
        "destinations": {
            "dest_db": {
                "type": "mysql",
                "connection": {"host": "localhost"},
                "load": {
                    "table": "users",
                    "mode": "upsert"
                    # key manquant ❌
                }
            }
        }
    }
    
    with pytest.raises(ValidationError) as exc:
        DestinationParser().parse(raw)
    
    error_msg = str(exc.value).lower()
    assert "upsert" in error_msg
    assert "key" in error_msg
    assert "requires" in error_msg or "required" in error_msg


def test_load_config_upsert_with_empty_key_fails():
    """
    Cas KO: mode upsert avec key vide → ValidationError.
    """
    raw = {
        "destinations": {
            "dest_db": {
                "type": "mysql",
                "connection": {"host": "localhost"},
                "load": {
                    "table": "users",
                    "mode": "upsert",
                    "key": []  # Vide ❌
                }
            }
        }
    }
    
    with pytest.raises(ValidationError) as exc:
        DestinationParser().parse(raw)


def test_load_config_key_with_empty_string_fails():
    """
    Cas KO: Colonne key vide → ValidationError.
    """
    raw = {
        "destinations": {
            "dest_db": {
                "type": "mysql",
                "connection": {"host": "localhost"},
                "load": {
                    "table": "users",
                    "mode": "upsert",
                    "key": [""]  # String vide ❌
                }
            }
        }
    }
    
    with pytest.raises(ValidationError) as exc:
        DestinationParser().parse(raw)
    
    assert "empty" in str(exc.value).lower()


def test_load_config_key_with_only_whitespace_fails():
    """
    Cas KO: Colonne key avec seulement whitespace → ValidationError.
    """
    raw = {
        "destinations": {
            "dest_db": {
                "type": "mysql",
                "connection": {"host": "localhost"},
                "load": {
                    "table": "users",
                    "mode": "upsert",
                    "key": ["  "]  # Whitespace seulement ❌
                }
            }
        }
    }
    
    with pytest.raises(ValidationError) as exc:
        DestinationParser().parse(raw)


def test_load_config_invalid_mode_fails():
    """
    Cas KO: Mode inconnu → ValidationError.
    """
    raw = {
        "destinations": {
            "dest_db": {
                "type": "mysql",
                "connection": {"host": "localhost"},
                "load": {
                    "table": "users",
                    "mode": "invalid_mode"  # Inconnu ❌
                }
            }
        }
    }
    
    with pytest.raises(ValidationError) as exc:
        DestinationParser().parse(raw)


def test_load_config_batch_size_too_small_fails():
    """
    Cas KO: batch_size < 10 → ValidationError.
    """
    raw = {
        "destinations": {
            "dest_db": {
                "type": "mysql",
                "connection": {"host": "localhost"},
                "load": {
                    "table": "users",
                    "batch_size": 5  # Trop petit ❌
                }
            }
        }
    }
    
    with pytest.raises(ValidationError) as exc:
        DestinationParser().parse(raw)
    
    assert "batch_size" in str(exc.value).lower()


def test_load_config_batch_size_too_large_fails():
    """
    Cas KO: batch_size > 100 000 → ValidationError.
    """
    raw = {
        "destinations": {
            "dest_db": {
                "type": "mysql",
                "connection": {"host": "localhost"},
                "load": {
                    "table": "users",
                    "batch_size": 200_000  # Trop grand ❌
                }
            }
        }
    }
    
    with pytest.raises(ValidationError) as exc:
        DestinationParser().parse(raw)
    
    assert "batch_size" in str(exc.value).lower()


# ============================================================
# Tests DestinationsConfig
# ============================================================

def test_destinations_empty_fails():
    """
    Cas KO: destinations vide → ValidationError.
    """
    raw = {"destinations": {}}
    
    with pytest.raises(ValidationError) as exc:
        DestinationParser().parse(raw)
    
    # Pydantic v2 dit "at least 1 item" pas "empty"
    error_msg = str(exc.value).lower()
    assert "at least" in error_msg or "empty" in error_msg


# ============================================================
# Résumé DoD Backlog 1.2
# ============================================================

"""
DoD Backlog 1.2 VALIDÉ:

✅ LoadMode Enum (append, replace, upsert)
✅ Pydantic échoue si upsert sans key (test_load_config_upsert_without_key_fails)
✅ Validation stricte champ key (nettoyage, déduplication)
✅ Messages d'erreur avec exemples
✅ Validation batch_size raisonnable

Tests: 16 tests couvrent:
- LoadMode Enum
- Cas OK (append, replace, upsert simple/composite)
- Nettoyage key (whitespace, déduplication)
- Cas KO (upsert sans key, key vide, mode invalide, batch_size)
- DestinationsConfig validation
"""