"""
Tests du parser destinations.yaml.

Objectifs :
- valider le schéma (structure et champs obligatoires)
- vérifier les défauts (mode, batch_size)
- vérifier les erreurs explicites (destinations vide, mode invalide, upsert sans key)
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from internal.parser.destination import DestinationParser


def test_destinations_parser_ok_minimal_append():
    """
    Cas OK : destination minimale avec load.table.
    """
    raw = {
        "destinations": {
            "dest_dwh": {
                "type": "mysql",
                "connection": {"host": "localhost", "port": 3306},
                "load": {"table": "orders_dwh"},
            }
        }
    }

    cfg = DestinationParser().parse(raw)
    assert "dest_dwh" in cfg.destinations
    assert cfg.destinations["dest_dwh"].type == "mysql"
    assert cfg.destinations["dest_dwh"].load.table == "orders_dwh"
    assert cfg.destinations["dest_dwh"].load.mode == "append"  # défaut
    assert cfg.destinations["dest_dwh"].load.batch_size == 10_000  # défaut


def test_destinations_parser_ok_replace():
    """
    Cas OK : mode=replace.
    """
    raw = {
        "destinations": {
            "dest_csv": {
                "type": "csv",
                "connection": {"path": "out.csv"},
                "load": {"table": "ignored_for_csv", "mode": "replace"},
            }
        }
    }

    cfg = DestinationParser().parse(raw)
    assert cfg.destinations["dest_csv"].load.mode == "replace"


def test_destinations_parser_ok_upsert_requires_key():
    """
    Cas OK : mode=upsert avec key.
    """
    raw = {
        "destinations": {
            "dest_db": {
                "type": "mariadb",
                "connection": {"host": "db"},
                "load": {"table": "t", "mode": "upsert", "key": ["id"]},
            }
        }
    }

    cfg = DestinationParser().parse(raw)
    assert cfg.destinations["dest_db"].load.mode == "upsert"
    assert cfg.destinations["dest_db"].load.key == ["id"]


def test_destinations_parser_rejects_empty_destinations():
    """
    Cas KO : destinations vide.
    """
    raw = {"destinations": {}}
    with pytest.raises(ValidationError):
        DestinationParser().parse(raw)


def test_destinations_parser_rejects_invalid_mode():
    """
    Cas KO : mode inconnu.
    """
    raw = {
        "destinations": {
            "dest_bad": {
                "type": "mysql",
                "connection": {"host": "localhost"},
                "load": {"table": "t", "mode": "invalid_mode"},
            }
        }
    }

    with pytest.raises(ValidationError):
        DestinationParser().parse(raw)


def test_destinations_parser_rejects_upsert_without_key():
    """
    Cas KO : upsert sans key.
    """
    raw = {
        "destinations": {
            "dest_bad": {
                "type": "mysql",
                "connection": {"host": "localhost"},
                "load": {"table": "t", "mode": "upsert"},
            }
        }
    }

    with pytest.raises(ValidationError):
        DestinationParser().parse(raw)


def test_destinations_parser_rejects_too_small_batch_size():
    """
    Cas KO : batch_size trop petit.
    """
    raw = {
        "destinations": {
            "dest_bad": {
                "type": "mysql",
                "connection": {"host": "localhost"},
                "load": {"table": "t", "batch_size": 1},
            }
        }
    }

    with pytest.raises(ValidationError):
        DestinationParser().parse(raw)
