"""Source MySQL CDC, testée sur un vrai serveur MySQL (binlog ROW).

Le serveur est lu dans HYDRA_TEST_MYSQL (host:port, utilisateur root sans mot de
passe par défaut : HYDRA_TEST_MYSQL_USER / HYDRA_TEST_MYSQL_PASSWORD) ; les tests
sont sautés si aucun serveur ne répond."""
from __future__ import annotations

import datetime as dt
import decimal
import json
import os

import pytest

pymysql = pytest.importorskip("pymysql")
pytest.importorskip("pymysqlreplication")

from hydra_etl.internal.connector.mysql_cdc_connector import MySQLCDCConnector  # noqa: E402
from hydra_etl.internal.connector.registry import build_connector  # noqa: E402

HOST, _, PORT = os.environ.get("HYDRA_TEST_MYSQL", "127.0.0.1:3306").partition(":")
USER = os.environ.get("HYDRA_TEST_MYSQL_USER", "root")
PASSWORD = os.environ.get("HYDRA_TEST_MYSQL_PASSWORD", "")


def _server():
    try:
        return pymysql.connect(host=HOST, port=int(PORT or 3306), user=USER, password=PASSWORD,
                               autocommit=True, connect_timeout=3)
    except Exception:  # noqa: BLE001
        pytest.skip("no MySQL server for the CDC tests (set HYDRA_TEST_MYSQL=host:port)")


@pytest.fixture()
def db():
    c = _server()
    cur = c.cursor()
    cur.execute("DROP DATABASE IF EXISTS hydra_cdc_test")
    cur.execute("CREATE DATABASE hydra_cdc_test")
    cur.execute("USE hydra_cdc_test")
    cur.execute("""CREATE TABLE orders (id INT PRIMARY KEY, amount DECIMAL(12,2), name VARCHAR(50),
                   ts DATETIME(6), payload JSON)""")
    cur.execute("CREATE TABLE other (id INT PRIMARY KEY)")
    cur.execute("INSERT INTO orders VALUES (1, 10.25, 'a', '2026-01-31 10:00:00.123456', '{\"k\": [1, 2]}'),"
                " (2, 3.00, 'b', NULL, NULL)")
    yield cur
    cur.execute("DROP DATABASE IF EXISTS hydra_cdc_test")
    c.close()


def _connector(tmp_path, **extra):
    return build_connector(name="orders_changes", config={
        "type": "mysql_cdc", "job_dir": str(tmp_path),
        "connection": {"host": HOST, "port": int(PORT or 3306), "user": USER, "password": PASSWORD,
                       "database": "hydra_cdc_test", **extra}})


def _read(conn, **kw):
    return [r for b in conn.extract_batches(table="orders", **kw) for r in b]


def test_registry_and_required_keys(tmp_path):
    assert isinstance(_connector(tmp_path), MySQLCDCConnector)
    with pytest.raises(ValueError, match="connection.database is required"):
        build_connector(name="x", config={"type": "mysql_cdc", "connection": {"user": "u"}})
    with pytest.raises(ValueError, match="state must be"):
        _connector(tmp_path, state="a/b")
    c = _connector(tmp_path)
    with pytest.raises(ValueError, match="cannot be a destination"):
        c.begin_load(table="t")
    with pytest.raises(ValueError, match="not a query"):
        list(c.extract_batches(query="SELECT 1"))


def test_first_run_snapshot_then_changes(db, tmp_path):
    c = _connector(tmp_path)
    rows = _read(c)
    assert [(r["id"], r["_op"]) for r in rows] == [(1, "snapshot"), (2, "snapshot")]
    assert rows[0]["amount"] == decimal.Decimal("10.25")
    assert rows[0]["ts"] == dt.datetime(2026, 1, 31, 10, 0, 0, 123456)
    assert c.confirm_extract()
    saved = json.loads(c.state_path.read_text())
    assert saved["log_file"] and saved["log_pos"] > 0

    db.execute("INSERT INTO orders VALUES (3, 7.50, 'c', NULL, '{\"x\": 1}')")
    db.execute("UPDATE orders SET name = 'A' WHERE id = 1")
    db.execute("DELETE FROM orders WHERE id = 2")
    db.execute("INSERT INTO other VALUES (9)")                      # autre table : ignorée
    c2 = _connector(tmp_path)
    changes = _read(c2)
    assert [(r["id"], r["_op"]) for r in changes] == [(3, "insert"), (1, "update"), (2, "delete")]
    assert changes[0]["amount"] == decimal.Decimal("7.50")
    assert changes[1]["name"] == "A" and changes[1]["amount"] == decimal.Decimal("10.25")   # ligne entière
    assert all(isinstance(r["_commit_time"], dt.datetime) and r["_commit_time"].tzinfo for r in changes)
    assert all(r["_lsn"].count(":") == 1 for r in changes)

    # sans confirmation : les mêmes changements sont relus
    assert [(r["id"], r["_op"]) for r in _read(_connector(tmp_path))] == [(3, "insert"), (1, "update"), (2, "delete")]
    assert c2.confirm_extract()
    assert _read(_connector(tmp_path)) == []


def test_transaction_emitted_whole(db, tmp_path):
    c = _connector(tmp_path, snapshot=False)
    assert _read(c) == []
    c.confirm_extract()
    db.execute("START TRANSACTION")
    db.execute("INSERT INTO orders (id, name) VALUES (10, 'x')")
    db.execute("INSERT INTO orders (id, name) VALUES (11, 'y')")
    db.execute("COMMIT")
    got = _read(_connector(tmp_path), batch_size=1)
    assert [r["id"] for r in got] == [10, 11]
    assert got[0]["_commit_time"] == got[1]["_commit_time"]


def test_row_image_must_be_full(db, tmp_path):
    db.execute("SET GLOBAL binlog_row_image = 'MINIMAL'")
    try:
        with pytest.raises(ValueError, match="binlog_row_image is 'MINIMAL'"):
            _read(_connector(tmp_path))
    finally:
        db.execute("SET GLOBAL binlog_row_image = 'FULL'")


def test_purged_position_fails_with_the_steps(db, tmp_path):
    c = _connector(tmp_path)
    c._write_state("binlog.999999", 4)
    with pytest.raises(ValueError, match="was purged by MySQL"):
        _read(c)
    assert c.cdc_status()["status"] == "lost"


def test_cdc_status(db, tmp_path):
    c = _connector(tmp_path)
    assert c.cdc_status()["status"] == "missing"
    _read(c)
    c.confirm_extract()
    db.execute("INSERT INTO orders (id) VALUES (20)")
    st = _connector(tmp_path).cdc_status()
    assert st["status"] == "ok" and st["lag_bytes"] > 0


def test_state_file_in_project(db, tmp_path):
    (tmp_path / ".hydra").mkdir()
    (tmp_path / ".hydra" / "project.json").write_text("{}")
    job = tmp_path / "jobs" / "mirror"
    job.mkdir(parents=True)
    c = build_connector(name="src", config={"type": "mysql_cdc", "job_dir": str(job), "connection": {
        "host": HOST, "port": int(PORT or 3306), "user": USER, "password": PASSWORD,
        "database": "hydra_cdc_test"}})
    assert c.state_path == tmp_path / ".hydra" / "cdc" / "mirror.src.json"


def test_generic_conditions(db, tmp_path):
    """cdc.lag / cdc.status : mêmes conditions pour toutes les sources CDC."""
    from hydra_etl.workflow import probes
    from hydra_etl.workflow.conditions import FUNCTIONS
    assert "cdc.lag" in FUNCTIONS and "cdc.status" in FUNCTIONS
    c = _connector(tmp_path)

    class Ctx:
        pass
    orig = probes._connector
    probes._connector = lambda kind, arg, ctx: (c, "mysql_cdc", {})
    try:
        assert probes.probe_cdc_status("orders_changes", Ctx())[0] == "missing"
        assert probes.probe_cdc_lag("orders_changes", Ctx())[0] == 0
        _read(c)
        c.confirm_extract()
        db.execute("INSERT INTO orders (id) VALUES (30)")
        assert probes.probe_cdc_status("orders_changes", Ctx())[0] == "ok"
        assert probes.probe_cdc_lag("orders_changes", Ctx())[0] > 0
    finally:
        probes._connector = orig
