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


# ── Annulation après publication (rollback: true, étape 5a) ─────────────────
from hydra_etl.internal.connector.undo import UndoConflict, UndoUnavailable  # noqa: E402


def _publish(c, mode, rows, key=None, table="atomic_t"):
    s = c.begin_load(table=table, mode=mode, key=key, atomic=True, undo=True)
    s.stage(rows)
    s.publish()
    return s.undo_record


@pytest.mark.parametrize("db", ["pg", "my"])
def test_undo_replace_append_upsert(db, request):
    c, rows = request.getfixturevalue(db)
    rec = _publish(c, "replace", [{"id": 5, "v": "new"}])
    assert rows() == [(5, "new")] and rec.backup_table
    assert "restored" in rec.undo(c)
    assert rows() == [(1, "old")]
    assert not c._table_exists(c._connect().cursor(), rec.backup_table)

    rec = _publish(c, "append", [{"id": 2, "v": "a"}, {"id": 3, "v": "b"}], key=["id"])
    assert rows() == [(1, "old"), (2, "a"), (3, "b")]
    rec.undo(c)
    assert rows() == [(1, "old")]

    rec = _publish(c, "upsert", [{"id": 1, "v": "upd"}, {"id": 4, "v": "ins"}], key=["id"])
    assert rows() == [(1, "upd"), (4, "ins")]
    rec.undo(c)
    assert rows() == [(1, "old")]


@pytest.mark.parametrize("db", ["pg", "my"])
def test_undo_refuses_when_someone_else_wrote(db, request):
    c, rows = request.getfixturevalue(db)
    rec = _publish(c, "replace", [{"id": 5, "v": "new"}])
    s = c.begin_load(table="atomic_t", mode="append", atomic=True)
    s.stage([{"id": 6, "v": "other"}])
    s.publish()
    with pytest.raises(UndoConflict, match="changed after this run"):
        rec.undo(c)
    assert rows() == [(5, "new"), (6, "other")]
    rec.discard(c)


@pytest.mark.parametrize("db", ["pg", "my"])
def test_append_with_undo_needs_new_keys(db, request):
    c, rows = request.getfixturevalue(db)
    with pytest.raises(UndoUnavailable, match="needs load.key"):
        c.begin_load(table="atomic_t", mode="append", atomic=True, undo=True)
    s = c.begin_load(table="atomic_t", mode="append", key=["id"], atomic=True, undo=True)
    with pytest.raises(ValueError, match="have a key already"):
        s.stage([{"id": 1, "v": "dup"}])
    s.abort()
    assert rows() == [(1, "old")]


def test_pg_undo_of_a_created_table_and_identity_columns(pg):
    c, rows = pg
    conn = c._connect()
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS atomic_new; DROP TABLE IF EXISTS atomic_id;"
                "CREATE TABLE atomic_id (id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY, v text);"
                "INSERT INTO atomic_id (v) VALUES ('old');")
    conn.commit()
    rec = _publish(c, "replace", [{"id": 1, "v": "x"}], table="atomic_new")
    assert rec.created
    rec.undo(c)
    assert not c._table_exists(cur, "atomic_new")
    rec = _publish(c, "replace", [{"v": "new"}], table="atomic_id")
    rec.undo(c)
    cur.execute("SELECT id, v FROM atomic_id")
    assert [(r["id"], r["v"]) for r in cur.fetchall()] == [(1, "old")]
    conn.close()
