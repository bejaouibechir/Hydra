"""
Régression : politiques de dérive MongoDB (drift_policy warn / fail / adapt).

Défaut corrigé (0.16.0) :
1. le bloc `schema` de sources.yaml n'atteignait pas le connecteur
   (JobExecutor._build_connector) ;
2. extract_batches() normalisait sans contrôler la dérive : un champ absent
   de l'échantillon d'inférence disparaissait en silence, quelle que soit la
   politique.

Scénario du rapport : 102 documents ; les 100 premiers ont _id, customer,
amount ; les deux derniers ajoutent sales_channel (web, store) ;
mode infer_strict, sample_size 100.

Aucun serveur MongoDB : la collection est remplacée par un faux curseur en
mémoire. Le transfert complet avec un vrai serveur reste à tester à part.

Run with: pytest tests/test_mongodb_drift.py -v
"""
from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

pytest.importorskip("pymongo")

from hydra_etl.internal.parser.source import SourceParser
from hydra_etl.internal.runner.executor import JobExecutor
from hydra_etl.internal.schema import SchemaDriftError
from hydra_etl.plugins.connectors.mongodb import MongoDBConnector


# ------------------------------------------------------------------
# Faux curseur / fausse collection
# ------------------------------------------------------------------

class _Cursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def limit(self, n):
        return _Cursor(self._docs[:n] if n else self._docs)

    def __iter__(self):
        return iter([dict(d) for d in self._docs])


class _Collection:
    def __init__(self, docs):
        self._docs = docs

    def find(self, _filter=None):
        return _Cursor(self._docs)


def _documents():
    docs = [{"_id": i, "customer": f"c{i}", "amount": float(i)} for i in range(100)]
    docs.append({"_id": 100, "customer": "c100", "amount": 100.0, "sales_channel": "web"})
    docs.append({"_id": 101, "customer": "c101", "amount": 101.0, "sales_channel": "store"})
    return docs


def _sources_yaml(policy: str) -> dict:
    return {
        "version": "1.0",
        "sources": {
            "orders": {
                "type": "mongodb",
                "connection": {"uri": "mongodb://localhost:27017", "database": "shop"},
                "extract": {"collection": "orders"},
                "schema": {"mode": "infer_strict", "sample_size": 100, "drift_policy": policy},
            }
        },
    }


def _connector_via_executor(policy: str) -> MongoDBConnector:
    """Chemin réel : sources.yaml -> SourceParser -> JobExecutor._build_connector."""
    cfg = SourceParser().parse(_sources_yaml(policy))
    definition = cfg.sources["orders"]
    fake_self = SimpleNamespace(path_base=".")
    conn = JobExecutor._build_connector(fake_self, "orders", definition, True)
    conn.client = object()                       # pas de connexion réelle
    conn.collection = _Collection(_documents())
    return conn


def _rows(conn) -> list:
    return [r for batch in conn.extract_batches() for r in batch]


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------

def test_schema_block_reaches_connector():
    conn = _connector_via_executor("fail")
    assert conn.config.get("schema", {}).get("drift_policy") == "fail"
    assert conn.drift_policy.value == "fail"
    assert conn.schema_mode.value == "infer_strict"
    assert conn.sample_size == 100


def test_drift_warn_keeps_rows_and_warns(caplog):
    conn = _connector_via_executor("warn")
    with caplog.at_level(logging.WARNING):
        rows = _rows(conn)
    assert len(rows) == 102
    assert all("sales_channel" not in r for r in rows)
    drift = [m for m in caplog.messages if "schema drift" in m and "sales_channel" in m]
    assert drift, "aucun avertissement de dérive émis"
    # une alerte au premier document concerné + un bilan, pas une par document
    assert len(drift) == 2
    assert "document #101" in drift[0]
    assert "(2 doc.)" in drift[1]


def test_drift_fail_stops_extraction():
    conn = _connector_via_executor("fail")
    with pytest.raises(SchemaDriftError) as exc:
        _rows(conn)
    msg = str(exc.value)
    assert "sales_channel" in msg
    assert "document #101" in msg
    assert "drift_policy: fail" in msg


def test_drift_adapt_keeps_new_field_and_values():
    conn = _connector_via_executor("adapt")
    rows = _rows(conn)
    assert len(rows) == 102
    by_id = {r["_id"]: r for r in rows}
    assert by_id[100]["sales_channel"] == "web"
    assert by_id[101]["sales_channel"] == "store"
    assert by_id[0].get("sales_channel") is None
    assert conn.schema.get_field("sales_channel") is not None
    assert conn.schema.get_field("sales_channel").required is False


def test_drift_ignore_is_silent(caplog):
    conn = _connector_via_executor("ignore")
    with caplog.at_level(logging.WARNING):
        rows = _rows(conn)
    assert len(rows) == 102
    assert not [m for m in caplog.messages if "schema drift" in m]


def test_no_drift_no_message(caplog):
    conn = _connector_via_executor("fail")
    conn.collection = _Collection(_documents()[:100])
    with caplog.at_level(logging.WARNING):
        rows = _rows(conn)
    assert len(rows) == 100


def test_manual_mode_is_not_drift():
    """En mode manual, le schéma déclaré est le contrat : les autres champs
    sont écartés par conception, même avec drift_policy: fail."""
    raw = _sources_yaml("fail")
    raw["sources"]["orders"]["schema"] = {
        "mode": "manual", "drift_policy": "fail",
        "fields": [{"name": "order_id", "path": "_id", "type": "integer"},
                   {"name": "amount", "type": "float"}],
    }
    definition = SourceParser().parse(raw).sources["orders"]
    conn = JobExecutor._build_connector(SimpleNamespace(path_base="."), "orders", definition, True)
    conn.client = object()
    conn.collection = _Collection(_documents())
    rows = _rows(conn)
    assert len(rows) == 102
    assert set(rows[-1]) == {"order_id", "amount"}


def test_nested_field_covered_by_parent_is_not_drift():
    conn = _connector_via_executor("fail")
    docs = [{"_id": i, "customer": {"name": f"n{i}"}} for i in range(5)]
    conn.collection = _Collection(docs)
    rows = _rows(conn)
    assert len(rows) == 5
