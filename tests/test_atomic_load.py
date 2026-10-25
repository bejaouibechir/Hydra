"""Chargement en tout ou rien par job (étape 4 du fallback) :
begin → stage → publish | abort (internal/connector/load_session.py)."""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import pytest

from hydra_etl.internal.connector.csv_connector import CSVConnector
from hydra_etl.internal.connector.load_session import (
    AtomicLoadError, LegacyLoadSession, cleanup_orphans, open_load_session, resolve_atomic,
    temp_path_for,
)
from hydra_etl.internal.connector.mysql_mariadb_connector import MySQLMariaDBConnector
from hydra_etl.internal.connector.postgresql_connector import PostgreSQLConnector
from hydra_etl.internal.connector.sqlserver_connector import SQLServerConnector
from hydra_etl.internal.runner.executor import JobExecutor

DB = {"connection": {"host": "h", "user": "u", "password": "p", "database": "db"}}


def csv_conn(tmp_path):
    return CSVConnector(name="dest", config={"type": "csv", "base_path": str(tmp_path)})


# ── Choix du tout ou rien ──────────────────────────────────────────────────
def test_defaults_per_connector(tmp_path):
    db = PostgreSQLConnector(name="pg", config={"type": "postgresql", **DB})
    assert resolve_atomic(db, "replace", None) == (True, None)
    assert resolve_atomic(db, "append", None) == (False, None)
    assert resolve_atomic(db, "upsert", True) == (True, None)
    assert resolve_atomic(db, "replace", False) == (False, None)
    c = csv_conn(tmp_path)
    assert resolve_atomic(c, "append", None) == (True, None)
    assert resolve_atomic(c, "replace", None) == (True, None)


class _Plain:
    """Connecteur sans session propre (plugin, API web…)."""
    name = "api"

    def __init__(self):
        self.calls = []

    def load_batches(self, batches, *, table, mode, key=None):
        self.calls.append((mode, [len(b) for b in batches]))


def test_unsupported_connector_is_explicit():
    p = _Plain()
    atomic, note = resolve_atomic(p, "replace", None)
    assert atomic is False and "cannot replace in all-or-nothing" in note
    assert resolve_atomic(p, "append", None) == (False, None)
    with pytest.raises(AtomicLoadError, match="atomic: true"):
        resolve_atomic(p, "append", True)
    s = open_load_session(p, table="t", mode="replace", key=None, atomic=False)
    assert isinstance(s, LegacyLoadSession)
    for b in ([{"a": 1}], [{"a": 2}], []):
        s.stage(b)
    s.publish()
    assert p.calls == [("replace", [1]), ("append", [1])]      # comme avant : replace puis append


# ── CSV ────────────────────────────────────────────────────────────────────
def test_csv_replace_is_all_or_nothing(tmp_path):
    out = tmp_path / "out.csv"
    out.write_text("id\nold\n", encoding="utf-8")
    c = csv_conn(tmp_path)
    s = c.begin_load(table="out.csv", mode="replace", atomic=True)
    s.stage([{"id": 1}, {"id": 2}])
    assert out.read_text(encoding="utf-8") == "id\nold\n"           # rien de visible avant publish
    s.abort()
    assert out.read_text(encoding="utf-8") == "id\nold\n"
    assert not list(tmp_path.glob(".out.csv.hydra-tmp-*"))

    s = c.begin_load(table="out.csv", mode="replace", atomic=True)
    s.stage([{"id": 1}])
    s.stage([{"id": 2}])
    s.publish()
    assert out.read_text(encoding="utf-8").splitlines() == ["id", "1", "2"]
    assert not list(tmp_path.glob(".out.csv.hydra-tmp-*"))


def test_csv_append_goes_back_to_the_original_size(tmp_path):
    out = tmp_path / "out.csv"
    out.write_text("id\n1\n", encoding="utf-8")
    c = csv_conn(tmp_path)
    s = c.begin_load(table="out.csv", mode="append", atomic=True)
    s.stage([{"id": 2}])
    s.abort()
    assert out.read_text(encoding="utf-8") == "id\n1\n"
    # fichier absent au départ : supprimé
    s = c.begin_load(table="new.csv", mode="append", atomic=True)
    s.stage([{"id": 2}])
    s.abort()
    assert not (tmp_path / "new.csv").exists()
    s = c.begin_load(table="out.csv", mode="append", atomic=True)
    s.stage([{"id": 2}])
    s.publish()
    assert out.read_text(encoding="utf-8").splitlines() == ["id", "1", "2"]


def test_csv_without_atomic_keeps_the_old_behaviour(tmp_path):
    out = tmp_path / "out.csv"
    out.write_text("id\nold\n", encoding="utf-8")
    s = csv_conn(tmp_path).begin_load(table="out.csv", mode="replace", atomic=False)
    s.stage([{"id": 1}])
    s.abort()
    assert out.read_text(encoding="utf-8").splitlines() == ["id", "1"]
    assert s.partial_write is True


def test_same_destination_is_written_by_one_job_at_a_time(tmp_path):
    c = csv_conn(tmp_path)
    order = []
    s1 = c.begin_load(table="out.csv", mode="append", atomic=True)

    def second():
        s2 = c.begin_load(table="out.csv", mode="append", atomic=True)
        order.append("s2 open")
        s2.stage([{"id": 2}])
        s2.publish()

    t = threading.Thread(target=second)
    t.start()
    time.sleep(0.2)
    order.append("s1 publish")
    s1.stage([{"id": 1}])
    s1.publish()
    t.join(5)
    assert order == ["s1 publish", "s2 open"]
    assert (tmp_path / "out.csv").read_text(encoding="utf-8").splitlines() == ["id", "1", "2"]


def test_orphans_of_dead_processes_are_removed(tmp_path):
    target = tmp_path / "out.csv"
    dead = target.with_name(f".out.csv.hydra-tmp-999999999-abcd1234")
    dead.write_text("x")
    mine = temp_path_for(target)
    mine.write_text("x")
    removed = cleanup_orphans(target)
    if os.name == "posix":
        assert removed == [dead] and not dead.exists()
    assert mine.exists()


# ── Parquet ────────────────────────────────────────────────────────────────
def test_parquet_session_keeps_one_writer_and_aborts_cleanly(tmp_path):
    pq = pytest.importorskip("pyarrow.parquet")
    from hydra_etl.internal.connector.parquet_connector import ParquetConnector
    c = ParquetConnector(name="p", config={"type": "parquet"}, job_dir=str(tmp_path)) \
        if "job_dir" in ParquetConnector.__init__.__code__.co_varnames else ParquetConnector(name="p", config={"type": "parquet"})
    path = tmp_path / "out.parquet"
    s = c.begin_load(table=str(path), mode="replace", atomic=True)
    for i in range(3):
        s.stage([{"id": i}])
    s.publish()
    assert pq.read_table(path).num_rows == 3
    s = c.begin_load(table=str(path), mode="append", atomic=True)
    s.stage([{"id": 9}])
    s.abort()
    assert pq.read_table(path).num_rows == 3
    s = c.begin_load(table=str(path), mode="append", atomic=True)
    s.stage([{"id": 9}])
    s.publish()
    assert pq.read_table(path).num_rows == 4
    assert not list(tmp_path.glob(".out.parquet.hydra-tmp-*"))


# ── Bases (connexions simulées) ────────────────────────────────────────────
class _Cur:
    def __init__(self, log, answers):
        self.log, self.answers = log, answers

    def execute(self, sql, params=None):
        self.log.append(("execute", " ".join(sql.split())))

    def executemany(self, sql, values):
        self.log.append(("executemany", " ".join(sql.split())))
        if "boom" in str(list(values)):
            raise RuntimeError("insert failed")

    def fetchone(self):
        return self.answers.pop(0) if self.answers else None

    def close(self):
        pass


class _Conn:
    def __init__(self, log, answers):
        self.log, self.answers = log, answers

    def cursor(self):
        return _Cur(self.log, self.answers)

    def commit(self):
        self.log.append(("commit",))

    def rollback(self):
        self.log.append(("rollback",))

    def close(self):
        self.log.append(("close",))


def _db(cls, kind, monkeypatch, answers=()):
    c = cls(name="d", config={"type": kind, **DB})
    log = []
    monkeypatch.setattr(c, "_connect", lambda: _Conn(log, list(answers)))
    return c, log


def verbs(log):
    return [e[0] if e[0] != "execute" else e[1].split()[0] for e in log]


def test_sqlserver_atomic_replace_is_one_transaction(monkeypatch):
    c, log = _db(SQLServerConnector, "sqlserver", monkeypatch)
    s = c.begin_load(table="t", mode="replace", atomic=True)
    s.stage([{"id": 1}])
    s.stage([{"id": 2}])
    assert "commit" not in verbs(log)                      # TRUNCATE + inserts non validés
    s.publish()
    assert verbs(log).count("commit") == 1 and verbs(log)[-2:] == ["commit", "close"]

    log.clear()
    s = c.begin_load(table="t", mode="replace", atomic=True)
    s.stage([{"id": 1}])
    with pytest.raises(ValueError, match="load failed"):
        s.stage([{"id": "boom"}])
    s.abort()
    assert "commit" not in verbs(log) and "rollback" in verbs(log)


def test_sqlserver_without_atomic_commits_every_batch(monkeypatch):
    c, log = _db(SQLServerConnector, "sqlserver", monkeypatch)
    s = c.begin_load(table="t", mode="append", atomic=False)
    s.stage([{"id": 1}])
    s.stage([{"id": 2}])
    s.publish()
    assert verbs(log).count("commit") >= 3
    assert s.batches_committed == 2


def test_postgresql_atomic_replace_truncates_inside_the_transaction(monkeypatch):
    c, log = _db(PostgreSQLConnector, "postgresql", monkeypatch, answers=[{"exists": True}])
    s = c.begin_load(table="t", mode="replace", atomic=True)
    s.stage([{"id": 1}])
    s.abort()
    v = verbs(log)
    assert "TRUNCATE" in v and "commit" not in v and "rollback" in v


def test_mysql_atomic_replace_uses_delete_and_needs_innodb(monkeypatch):
    c, log = _db(MySQLMariaDBConnector, "mysql", monkeypatch, answers=[("InnoDB",)])
    s = c.begin_load(table="t", mode="replace", atomic=True)
    s.stage([{"id": 1}])
    s.publish()
    v = verbs(log)
    assert "DELETE" in v and "TRUNCATE" not in v and v.count("commit") == 1
    c, log = _db(MySQLMariaDBConnector, "mysql", monkeypatch, answers=[("MyISAM",)])
    with pytest.raises(ValueError, match="MyISAM engine, which has no transactions"):
        c.begin_load(table="t", mode="replace", atomic=True)
    assert "close" in verbs(log)
    c, log = _db(MySQLMariaDBConnector, "mysql", monkeypatch)
    s = c.begin_load(table="t", mode="replace", atomic=False)
    assert "TRUNCATE" in verbs(log)
    s.abort()


# ── Job complet ────────────────────────────────────────────────────────────
def _job(tmp_path: Path, atomic=None) -> Path:
    job = tmp_path / "job"
    (job / "data").mkdir(parents=True)
    rows = "\n".join(f"{i},{i * 10}" for i in range(1, 301))
    (job / "data" / "in.csv").write_text("id,value\n" + rows + "\n", encoding="utf-8")
    (job / "data" / "out.csv").write_text("id,value\nold,0\n", encoding="utf-8")
    (job / "sources.yaml").write_text(
        "sources:\n  src:\n    type: csv\n    extract:\n      table: data/in.csv\n      batch_size: 100\n",
        encoding="utf-8")
    extra = "" if atomic is None else f"      atomic: {str(atomic).lower()}\n"
    (job / "destinations.yaml").write_text(
        "destinations:\n  dst:\n    type: csv\n    load:\n      table: data/out.csv\n"
        "      mode: replace\n" + extra, encoding="utf-8")
    (job / "pipeline.yaml").write_text("pipeline:\n  from: src\n  to: dst\n", encoding="utf-8")
    (job / "transformations.yaml").write_text(
        "steps:\n  - cast:\n      mapping:\n        value: float\n", encoding="utf-8")
    return job


def _fail_on_batch(monkeypatch, n, exc=RuntimeError("boom")):
    real = JobExecutor._run_steps
    calls = {"n": 0}

    def run_steps(self, df, *a, **k):
        calls["n"] += 1
        if calls["n"] == n:
            raise exc
        return real(self, df, *a, **k)
    monkeypatch.setattr(JobExecutor, "_run_steps", run_steps)


def test_failed_job_leaves_the_destination_unchanged(tmp_path, monkeypatch):
    job = _job(tmp_path)
    _fail_on_batch(monkeypatch, 3)
    r = JobExecutor(job_dir=str(job)).run()
    assert not r.success and r.atomic is True and r.partial_write is False
    assert (job / "data" / "out.csv").read_text(encoding="utf-8") == "id,value\nold,0\n"


def test_failed_job_without_atomic_reports_a_partial_write(tmp_path, monkeypatch):
    job = _job(tmp_path, atomic=False)
    _fail_on_batch(monkeypatch, 3)
    r = JobExecutor(job_dir=str(job)).run()
    assert not r.success and r.atomic is False and r.partial_write is True
    assert len((job / "data" / "out.csv").read_text(encoding="utf-8").splitlines()) == 201


def test_successful_job_publishes_everything(tmp_path):
    job = _job(tmp_path)
    r = JobExecutor(job_dir=str(job)).run()
    assert r.success and r.atomic is True and r.rows_out == 300
    assert len((job / "data" / "out.csv").read_text(encoding="utf-8").splitlines()) == 301


def test_interrupted_job_is_cancelled(tmp_path, monkeypatch):
    job = _job(tmp_path)
    _fail_on_batch(monkeypatch, 2, KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        JobExecutor(job_dir=str(job)).run()
    assert (job / "data" / "out.csv").read_text(encoding="utf-8") == "id,value\nold,0\n"
    assert not list((job / "data").glob(".out.csv.hydra-tmp-*"))


def test_atomic_true_on_an_unsupported_mode_fails_before_reading(tmp_path):
    job = _job(tmp_path)
    (job / "destinations.yaml").write_text(
        "destinations:\n  dst:\n    type: csv\n    load:\n      table: data/out.csv\n"
        "      mode: upsert\n      key: [id]\n      atomic: true\n", encoding="utf-8")
    r = JobExecutor(job_dir=str(job)).run()
    assert not r.success and r.rows_in == 0
