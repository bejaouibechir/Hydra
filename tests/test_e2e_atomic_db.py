"""Tout ou rien sur de vraies bases (étape 4 du fallback).

Lancés seulement si une base de test est indiquée :
  HYDRA_TEST_PG="host=127.0.0.1 port=5432 user=postgres password=x database=hydra"
  HYDRA_TEST_MYSQL="host=127.0.0.1 port=3306 user=root password=x database=hydra"
"""
from __future__ import annotations

import os

import pytest

from hydra_etl.internal.connector.mysql_mariadb_connector import MySQLMariaDBConnector
from hydra_etl.internal.connector.postgresql_connector import PostgreSQLConnector


def _cfg(var):
    raw = os.environ.get(var)
    if not raw:
        pytest.skip(f"{var} not set")
    conn = dict(kv.split("=", 1) for kv in raw.split())
    conn["port"] = int(conn.get("port", 0)) or None
    return {"connection": {k: v for k, v in conn.items() if v is not None}}


@pytest.fixture
def pg():
    pytest.importorskip("psycopg2")
    c = PostgreSQLConnector(name="pg", config={"type": "postgresql", **_cfg("HYDRA_TEST_PG")})
    conn = c._connect()
    cur = conn.cursor()
    cur.execute("DROP VIEW IF EXISTS atomic_v; DROP TABLE IF EXISTS atomic_t;"
                "CREATE TABLE atomic_t (id int PRIMARY KEY, v text);"
                "INSERT INTO atomic_t VALUES (1, 'old');"
                "CREATE VIEW atomic_v AS SELECT * FROM atomic_t;")
    conn.commit()

    def rows(rel="atomic_t"):
        cur.execute(f"SELECT id, v FROM {rel} ORDER BY id")
        r = [(x["id"], x["v"]) for x in cur.fetchall()]
        conn.commit()
        return r
    yield c, rows
    conn.close()


@pytest.fixture
def my():
    pytest.importorskip("mysql.connector")
    c = MySQLMariaDBConnector(name="my", config={"type": "mysql", **_cfg("HYDRA_TEST_MYSQL")})
    conn = c._connect()
    cur = conn.cursor()
    for sql in ("DROP TABLE IF EXISTS atomic_t", "DROP TABLE IF EXISTS atomic_m",
                "CREATE TABLE atomic_t (id int PRIMARY KEY, v varchar(20)) ENGINE=InnoDB",
                "INSERT INTO atomic_t VALUES (1, 'old')",
                "CREATE TABLE atomic_m (id int PRIMARY KEY, v varchar(20)) ENGINE=MyISAM"):
        cur.execute(sql)
    conn.commit()

    def rows():
        conn.rollback()
        cur.execute("SELECT id, v FROM atomic_t ORDER BY id")
        return [tuple(r) for r in cur.fetchall()]
    yield c, rows
    conn.close()


def _fail_after_one_batch(c, mode, atomic, key=None):
    s = c.begin_load(table="atomic_t", mode=mode, key=key, atomic=atomic)
    s.stage([{"id": 2, "v": "new"}])
    with pytest.raises(ValueError):
        s.stage([{"id": "abc", "v": "x"}])          # entier invalide : échec du 2e lot
    s.abort()
    return s


def test_pg_replace_failure_keeps_the_table_and_its_view(pg):
    c, rows = pg
    s = _fail_after_one_batch(c, "replace", True)
    assert rows() == [(1, "old")] and rows("atomic_v") == [(1, "old")]
    assert not s.partial_write
    s = c.begin_load(table="atomic_t", mode="replace", atomic=True)
    s.stage([{"id": 2, "v": "a"}])
    s.stage([{"id": 3, "v": "b"}])
    s.publish()
    assert rows() == [(2, "a"), (3, "b")] and rows("atomic_v") == [(2, "a"), (3, "b")]


def test_pg_append_and_upsert_atomic(pg):
    c, rows = pg
    _fail_after_one_batch(c, "append", True)
    assert rows() == [(1, "old")]
    _fail_after_one_batch(c, "upsert", True, key=["id"])
    assert rows() == [(1, "old")]


def test_pg_without_atomic_keeps_the_written_batches(pg):
    c, rows = pg
    s = _fail_after_one_batch(c, "replace", False)
    assert rows() == [(2, "new")] and s.partial_write


def test_mysql_replace_failure_keeps_the_table(my):
    c, rows = my
    _fail_after_one_batch(c, "replace", True)
    assert rows() == [(1, "old")]
    s = c.begin_load(table="atomic_t", mode="replace", atomic=True)
    s.stage([{"id": 5, "v": "a"}])
    s.publish()
    assert rows() == [(5, "a")]


def test_mysql_append_atomic_and_myisam_refused(my):
    c, rows = my
    _fail_after_one_batch(c, "append", True)
    assert rows() == [(1, "old")]
    with pytest.raises(ValueError, match="MyISAM"):
        c.begin_load(table="atomic_m", mode="replace", atomic=True)


def test_mysql_without_atomic_keeps_the_written_batches(my):
    c, rows = my
    s = _fail_after_one_batch(c, "replace", False)
    assert rows() == [(2, "new")] and s.partial_write
