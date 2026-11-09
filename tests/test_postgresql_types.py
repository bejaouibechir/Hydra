"""PostgreSQL : types fidèles à la création automatique de table, clé primaire
en upsert, JSON. Partie live : HYDRA_TEST_PG="host=... port=... user=... password=... database=..."."""
from __future__ import annotations

import datetime as dt
import decimal
import os

import pytest

from hydra_etl.internal.connector.postgresql_connector import PostgreSQLConnector, _pg_type

UTC = dt.timezone.utc


@pytest.mark.parametrize("values,expected", [
    ([1, 2, None], "BIGINT"),
    ([1, 2 ** 70], "NUMERIC"),
    ([decimal.Decimal("10.25"), 3], "NUMERIC"),
    ([1.5, 2], "DOUBLE PRECISION"),
    ([True, False], "BOOLEAN"),
    ([dt.date(2026, 1, 31)], "DATE"),
    ([dt.datetime(2026, 1, 31, 10)], "TIMESTAMP"),
    ([dt.datetime(2026, 1, 31, 10, tzinfo=UTC)], "TIMESTAMPTZ"),
    ([dt.date(2026, 1, 31), dt.datetime(2026, 1, 31, 10)], "TIMESTAMP"),
    ([{"a": 1}, [1, 2]], "JSONB"),
    (["x", 1], "TEXT"),
    ([None, None], "TEXT"),
    ([float("nan"), 2.5], "DOUBLE PRECISION"),
])
def test_pg_type(values, expected):
    assert _pg_type(values) == expected


def _cfg():
    raw = os.environ.get("HYDRA_TEST_PG")
    if not raw:
        pytest.skip("HYDRA_TEST_PG not set")
    return {"connection": dict(p.split("=", 1) for p in raw.split())}


def _rows(amount_bump: int = 0):
    return [{
        "order_id": 9007199254740993 + i,
        "amount": decimal.Decimal("10.25") + amount_bump,
        "ordered_at": dt.datetime(2026, 10, 1, 7, 0, tzinfo=UTC),
        "shipped_on": dt.date(2026, 10, 3),
        "details": {"items": [{"sku": "A1", "qty": 2}]},
    } for i in range(3)]


def test_upsert_creates_table_with_exact_types_and_primary_key():
    c = PostgreSQLConnector(name="pg", config={"type": "postgresql", **_cfg()})
    conn = c._connect()
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS hydra_types_t")
    conn.commit()
    for bump in (0, 1):                              # 2e passage : la clé primaire sert l'upsert
        s = c.begin_load(table="hydra_types_t", mode="upsert", key=["order_id"], atomic=True)
        s.stage(_rows(bump))
        s.publish()
    cur.execute("""SELECT column_name, data_type FROM information_schema.columns
                   WHERE table_name = 'hydra_types_t' ORDER BY ordinal_position""")
    types = {r["column_name"]: r["data_type"] for r in cur.fetchall()}
    assert types == {"order_id": "bigint", "amount": "numeric",
                     "ordered_at": "timestamp with time zone", "shipped_on": "date",
                     "details": "jsonb"}
    cur.execute("SELECT count(*) AS n, min(order_id) AS m, sum(amount) AS s, "
                "max(details->'items'->0->>'sku') AS sku FROM hydra_types_t")
    r = cur.fetchone()
    assert (r["n"], r["m"], r["s"], r["sku"]) == (3, 9007199254740993, decimal.Decimal("33.75"), "A1")
    cur.execute("DROP TABLE hydra_types_t")
    conn.commit()
    conn.close()


def test_failed_atomic_upsert_into_new_table_leaves_nothing():
    c = PostgreSQLConnector(name="pg", config={"type": "postgresql", **_cfg()})
    conn = c._connect()
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS hydra_types_f")
    conn.commit()
    s = c.begin_load(table="hydra_types_f", mode="upsert", key=["order_id"], atomic=True)
    s.stage(_rows())
    with pytest.raises(Exception):
        s.stage([{**_rows()[0], "order_id": None}])  # clé NULL : refusée par la clé primaire
        s.publish()
    s.abort()
    cur.execute("SELECT to_regclass('public.hydra_types_f') AS t")
    assert cur.fetchone()["t"] is None               # même la table créée est annulée
    conn.close()


def test_integer_too_big_for_existing_column_is_explained_before_writing():
    c = PostgreSQLConnector(name="pg", config={"type": "postgresql", **_cfg()})
    conn = c._connect()
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS hydra_types_big")
    conn.commit()
    s = c.begin_load(table="hydra_types_big", mode="upsert", key=["order_id"], atomic=True)
    s.stage(_rows())
    s.publish()
    s = c.begin_load(table="hydra_types_big", mode="upsert", key=["order_id"], atomic=True)
    s.stage(_rows(1))
    with pytest.raises(ValueError) as e:
        s.stage([{**_rows()[0], "order_id": 12345678901234567890123}])
    s.abort()
    msg = str(e.value)
    assert "does not fit in column 'order_id', which is bigint" in msg
    assert "ALTER TABLE public.hydra_types_big ALTER COLUMN order_id TYPE NUMERIC(38,0)" in msg
    cur.execute("SELECT sum(amount) AS s FROM hydra_types_big")
    assert cur.fetchone()["s"] == decimal.Decimal("30.75")   # premier chargement intact
    cur.execute("DROP TABLE hydra_types_big")
    conn.commit()
    conn.close()


def test_upsert_with_duplicate_keys_in_a_batch_keeps_the_last_row():
    c = PostgreSQLConnector(name="pg", config={"type": "postgresql", **_cfg()})
    conn = c._connect()
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS hydra_types_dup")
    conn.commit()
    rows = [{"id": i % 3, "v": i, "doc": {"i": i}} for i in range(9)]   # chaque clé trois fois
    s = c.begin_load(table="hydra_types_dup", mode="upsert", key=["id"], atomic=True)
    s.stage(rows)
    s.publish()
    cur.execute("SELECT id, v, doc->>'i' AS i FROM hydra_types_dup ORDER BY id")
    assert [(r["id"], r["v"], r["i"]) for r in cur.fetchall()] == [(0, 6, "6"), (1, 7, "7"), (2, 8, "8")]
    cur.execute("DROP TABLE hydra_types_dup")
    conn.commit()
    conn.close()


def test_append_creates_a_missing_table_and_writes_many_rows():
    c = PostgreSQLConnector(name="pg", config={"type": "postgresql", **_cfg()})
    conn = c._connect()
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS hydra_types_app")
    conn.commit()
    s = c.begin_load(table="hydra_types_app", mode="append", atomic=True)
    for start in (0, 2500):                                  # plus d'une requête multi-lignes par lot
        s.stage([{"id": i, "amount": decimal.Decimal(i) / 100, "note": None if i % 2 else "x"}
                 for i in range(start, start + 2500)])
    s.publish()
    cur.execute("SELECT count(*) AS n, sum(amount) AS s, count(note) AS notes FROM hydra_types_app")
    r = cur.fetchone()
    assert (r["n"], r["s"], r["notes"]) == (5000, decimal.Decimal("124975.00"), 2500)
    cur.execute("DROP TABLE hydra_types_app")
    conn.commit()
    conn.close()
