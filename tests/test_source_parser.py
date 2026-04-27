"""
Tests du parser sources.yaml.

Objectifs :
- valider le schéma (structure et champs obligatoires)
- vérifier les défauts (batch_size)
- vérifier les erreurs explicites (source vide, extract incomplet)
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from internal.parser.source import SourceParser


def test_sources_parser_ok_minimal_table():
    """
    Cas OK : une source minimale avec extract.table.
    """
    raw = {
        "sources": {
            "src_orders": {
                "type": "mysql",
                "connection": {"host": "localhost", "port": 3306},
                "extract": {"table": "orders"},
            }
        }
    }

    cfg = SourceParser().parse(raw)
    assert "src_orders" in cfg.sources
    assert cfg.sources["src_orders"].type == "mysql"
    assert cfg.sources["src_orders"].extract.table == "orders"
    assert cfg.sources["src_orders"].extract.batch_size == 10_000  # défaut


def test_sources_parser_ok_query():
    """
    Cas OK : source avec extract.query.
    """
    raw = {
        "sources": {
            "src_custom": {
                "type": "mariadb",
                "connection": {"host": "db", "port": 3306},
                "extract": {"query": "select 1 as id"},
            }
        }
    }

    cfg = SourceParser().parse(raw)
    assert cfg.sources["src_custom"].extract.query == "select 1 as id"


def test_sources_parser_rejects_empty_sources():
    """
    Cas KO : sources vide.
    """
    raw = {"sources": {}}
    with pytest.raises(ValidationError):
        SourceParser().parse(raw)


def test_sources_parser_rejects_extract_without_table_or_query():
    """
    Cas KO : extract sans table ni query.
    """
    raw = {
        "sources": {
            "src_bad": {
                "type": "mysql",
                "connection": {"host": "localhost"},
                "extract": {"batch_size": 1000},
            }
        }
    }
    with pytest.raises(ValidationError):
        SourceParser().parse(raw)


def test_sources_parser_rejects_too_small_batch_size():
    """
    Cas KO : batch_size trop petit.
    """
    raw = {
        "sources": {
            "src_bad": {
                "type": "mysql",
                "connection": {"host": "localhost"},
                "extract": {"table": "t", "batch_size": 1},
            }
        }
    }
    with pytest.raises(ValidationError):
        SourceParser().parse(raw)
