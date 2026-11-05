"""Connecteur SQLite (0.20) : source, destination, tout ou rien, upsert, undo."""
from __future__ import annotations

import sqlite3
import textwrap
from pathlib import Path

import pytest

from hydra_etl.internal.connector.load_session import resolve_atomic
from hydra_etl.internal.connector.registry import build_connector
from hydra_etl.internal.connector.sqlite_connector import SQLiteConnector
from hydra_etl.internal.runner.executor import JobExecutor


def conn(tmp_path: Path, path: str = "app.db") -> SQLiteConnector:
    return build_connector(name="db", config={"type": "sqlite", "connection": {"path": path},
                                              "job_dir": str(tmp_path)})


def rows(db: Path, sql: str):
    c = sqlite3.connect(db)
    try:
        return c.execute(sql).fetchall()
    finally:
        c.close()


def load(c, batches, **kw):
    s = c.begin_load(**kw)
    try:
        for b in batches:
            s.stage(b)
        s.publish()
    except BaseException:
        s.abort()
        raise


# ── Configuration ──────────────────────────────────────────────────────────
def test_path_is_relative_to_the_job_folder(tmp_path):
    c = conn(tmp_path, "../data/app.db")
    assert c.path == (tmp_path.parent / "data" / "app.db").resolve()


def test_path_is_required(tmp_path):
    with pytest.raises(ValueError, match="connection.path is required"):
        build_connector(name="db", config={"type": "sqlite", "connection": {}, "job_dir": str(tmp_path)})


def test_all_modes_are_all_or_nothing_by_default(tmp_path):
    c = conn(tmp_path)
    for mode in ("append", "replace", "upsert"):
        assert resolve_atomic(c, mode, None) == (True, None)
    assert resolve_atomic(c, "append", False) == (False, None)


def test_test_connection_creates_nothing(tmp_path):
    c = conn(tmp_path, "new/app.db")
    c.test_connection()
    assert not (tmp_path / "new").exists()


# ── Destination ────────────────────────────────────────────────────────────
def test_table_is_created_with_types_and_primary_key_for_upsert(tmp_path):
    c = conn(tmp_path)
    load(c, [[{"id": 1, "name": "a", "v": 1.5}, {"id": 2, "name": "b", "v": 2}]],
         table="t", mode="upsert", key=["id"])
    ddl = rows(tmp_path / "app.db", "SELECT sql FROM sqlite_master WHERE name = 't'")[0][0]
    assert '"id" INTEGER' in ddl and '"name" TEXT' in ddl and '"v" REAL' in ddl
    assert 'PRIMARY KEY ("id")' in ddl
    load(c, [[{"id": 2, "name": "B", "v": 9.0}, {"id": 3, "name": "c", "v": 3.0}]],
         table="t", mode="upsert", key=["id"])
    assert rows(tmp_path / "app.db", "SELECT * FROM t ORDER BY id") == [
        (1, "a", 1.5), (2, "B", 9.0), (3, "c", 3.0)]


def test_replace_and_append(tmp_path):
    c = conn(tmp_path)
    load(c, [[{"id": 1}, {"id": 2}]], table="t", mode="replace")
    load(c, [[{"id": 3}]], table="t", mode="append")
    assert rows(tmp_path / "app.db", "SELECT id FROM t ORDER BY id") == [(1,), (2,), (3,)]
    load(c, [[{"id": 9}]], table="t", mode="replace")
    assert rows(tmp_path / "app.db", "SELECT id FROM t") == [(9,)]


def test_numpy_pandas_and_nan_values_are_bound(tmp_path):
    np = pytest.importorskip("numpy")
    pd = pytest.importorskip("pandas")
    c = conn(tmp_path)
    load(c, [[{"i": np.int64(5), "f": np.float64("nan"), "b": np.bool_(True),
               "d": pd.Timestamp("2026-11-05 10:00:00"), "n": None}]], table="t", mode="append")
    assert rows(tmp_path / "app.db", "SELECT i, f, b, d, n FROM t") == [
        (5, None, 1, "2026-11-05T10:00:00", None)]


def test_failure_in_a_later_batch_leaves_the_table_untouched(tmp_path):
    db = tmp_path / "app.db"
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v REAL NOT NULL)")
    c.execute("INSERT INTO t VALUES (1, 10.0)")
    c.commit(); c.close()
    with pytest.raises(ValueError, match="NOT NULL"):
        load(conn(tmp_path), [[{"id": 5, "v": 1.0}], [{"id": 6, "v": None}]], table="t", mode="replace",
             atomic=True)
    assert rows(db, "SELECT * FROM t") == [(1, 10.0)]


def test_abort_rolls_back_the_created_table_too(tmp_path):
    """Échec après un lot (transformation, Ctrl+C...) : la table créée par le
    job disparaît avec le reste de la transaction."""
    s = conn(tmp_path).begin_load(table="u", mode="append", atomic=True)
    s.stage([{"id": 1, "x": 1}])
    s.abort()
    assert rows(tmp_path / "app.db", "SELECT COUNT(*) FROM sqlite_master WHERE name = 'u'") == [(0,)]


def test_without_atomic_the_written_batches_stay(tmp_path):
    db = tmp_path / "app.db"
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE t (id INTEGER, v REAL NOT NULL)")
    c.commit(); c.close()
    s = conn(tmp_path).begin_load(table="t", mode="append", atomic=False)
    s.stage([{"id": 1, "v": 1.0}])
    with pytest.raises(ValueError, match="NOT NULL"):
        s.stage([{"id": 2, "v": None}])
    s.abort()
    assert s.partial_write
    assert rows(db, "SELECT id FROM t") == [(1,)]


def test_upsert_on_a_table_without_matching_key_is_explained(tmp_path):
    db = tmp_path / "app.db"
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE t (id INTEGER, v REAL)")
    c.commit(); c.close()
    with pytest.raises(ValueError, match="needs a PRIMARY KEY or a UNIQUE index on \\['id'\\]"):
        load(conn(tmp_path), [[{"id": 1, "v": 1.0}]], table="t", mode="upsert", key=["id"])


def test_upsert_without_key_is_refused(tmp_path):
    with pytest.raises(ValueError, match="needs load.key"):
        conn(tmp_path).begin_load(table="t", mode="upsert", key=None)


# ── Source ─────────────────────────────────────────────────────────────────
def test_source_table_and_query(tmp_path):
    db = tmp_path / "app.db"
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE t (id INTEGER, v REAL)")
    c.executemany("INSERT INTO t VALUES (?, ?)", [(i, i * 1.5) for i in range(250)])
    c.commit(); c.close()
    s = conn(tmp_path)
    batches = list(s.extract_batches(table="t", batch_size=100))
    assert [len(b) for b in batches] == [100, 100, 50]
    assert batches[0][1] == {"id": 1, "v": 1.5}
    got = [r for b in s.extract_batches(query="SELECT id FROM t WHERE id < 3") for r in b]
    assert got == [{"id": 0}, {"id": 1}, {"id": 2}]


def test_missing_source_file_is_reported_and_not_created(tmp_path):
    s = conn(tmp_path, "nope.db")
    with pytest.raises(ValueError, match="database file not found"):
        list(s.extract_batches(table="t"))
    assert not (tmp_path / "nope.db").exists()


# ── Job et workflow ────────────────────────────────────────────────────────
def _job(root: Path, name: str, src: str, dst: str, steps: str = "steps:\n  - select:\n      columns: [id, v]\n"):
    j = root / "jobs" / name
    j.mkdir(parents=True)
    (j / "sources.yaml").write_text(src, encoding="utf-8")
    (j / "destinations.yaml").write_text(dst, encoding="utf-8")
    (j / "pipeline.yaml").write_text("pipeline:\n  from: src\n  to: dst\n", encoding="utf-8")
    (j / "transformations.yaml").write_text(steps, encoding="utf-8")
    return j


def test_csv_to_sqlite_to_csv(tmp_path):
    (tmp_path / "in.csv").write_text("id,v\n1,1.5\n2,2.5\n", encoding="utf-8")
    j1 = _job(tmp_path, "load",
              "sources:\n  src:\n    type: csv\n    extract:\n      table: ../../in.csv\n",
              "destinations:\n  dst:\n    type: sqlite\n    connection:\n      path: ../../app.db\n"
              "    load:\n      table: t\n      mode: upsert\n      key: [id]\n",
              "steps:\n  - cast:\n      mapping:\n        id: int\n        v: float\n")
    assert JobExecutor(job_dir=str(j1)).run().success
    j2 = _job(tmp_path, "export",
              "sources:\n  src:\n    type: sqlite\n    connection:\n      path: ../../app.db\n"
              "    extract:\n      query: \"SELECT id, v FROM t WHERE v > 2\"\n",
              "destinations:\n  dst:\n    type: csv\n    load:\n      table: ../../out.csv\n      mode: replace\n")
    assert JobExecutor(job_dir=str(j2)).run().success
    assert (tmp_path / "out.csv").read_text(encoding="utf-8").splitlines() == ["id,v", "2,2.5"]


def test_workflow_rollback_removes_the_rows_of_a_failed_run(tmp_path):
    from hydra_etl.workflow.parser import load_workflow
    from hydra_etl.workflow.runner import WorkflowRunner
    (tmp_path / "in.csv").write_text("id,v\n1,1.5\n2,2.5\n", encoding="utf-8")
    _job(tmp_path, "load",
         "sources:\n  src:\n    type: csv\n    extract:\n      table: ../../in.csv\n",
         "destinations:\n  dst:\n    type: sqlite\n    connection:\n      path: ../../app.db\n"
         "    load:\n      table: t\n      mode: replace\n",
         "steps:\n  - cast:\n      mapping:\n        id: int\n        v: float\n")
    wf = tmp_path / "wf.yaml"
    wf.write_text(textwrap.dedent("""\
        workflow:
          name: w
          rollback: true
          steps:
            - name: load
              type: job
              job: jobs/load
            - name: boom
              type: action
              action: python
              undo: none
              params:
                script: "raise SystemExit(1)"
              depends_on: [load]
        """), encoding="utf-8")
    res = WorkflowRunner(load_workflow(wf), base_dir=tmp_path).run()
    assert not res.success
    # la table n'existait pas avant le run : le rollback la supprime
    assert rows(tmp_path / "app.db", "SELECT COUNT(*) FROM sqlite_master WHERE name = 't'") == [(0,)]


def test_same_file_read_and_write_in_one_job(tmp_path):
    """WAL : le job lit la table a pendant qu'il écrit la table b du même fichier."""
    db = tmp_path / "app.db"
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE a (id INTEGER, v REAL)")
    c.executemany("INSERT INTO a VALUES (?, ?)", [(i, float(i)) for i in range(2500)])
    c.commit(); c.close()
    j = _job(tmp_path, "copy",
             "sources:\n  src:\n    type: sqlite\n    connection:\n      path: ../../app.db\n"
             "    extract:\n      table: a\n      batch_size: 1000\n",
             "destinations:\n  dst:\n    type: sqlite\n    connection:\n      path: ../../app.db\n"
             "    load:\n      table: b\n      mode: replace\n")
    res = JobExecutor(job_dir=str(j)).run()
    assert res.success, res.error
    assert rows(db, "SELECT COUNT(*), SUM(v) FROM b") == [(2500, float(sum(range(2500))))]


def test_source_change_trigger_counts_with_sql(tmp_path):
    from hydra_etl.triggers.sources import _sql
    db = tmp_path / "app.db"
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE t (id INTEGER)")
    c.executemany("INSERT INTO t VALUES (?)", [(i,) for i in range(7)])
    c.commit(); c.close()
    s = conn(tmp_path)
    assert _sql(s, "sqlite", "t", None, "count", None) == "7"
    assert _sql(s, "sqlite", "t", None, "max", "id") == "6"
