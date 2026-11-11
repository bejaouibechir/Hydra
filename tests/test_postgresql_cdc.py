"""Source PostgreSQL CDC (réplication logique, pgoutput) vers une destination
PostgreSQL en upsert : instantané initial, insert / update / delete, panne en
plein chargement (rien n'est perdu), TOAST inchangé, décodage des types.

Partie live : HYDRA_TEST_PG="host=... port=... user=... password=... database=..."
sur un PostgreSQL 11+ avec wal_level = logical (sinon ignorée)."""
from __future__ import annotations

import datetime as dt
import decimal
import os
from pathlib import Path

import pytest

from hydra_etl.internal.connector.postgresql_cdc_connector import (
    UNCHANGED, PostgreSQLCDCConnector, _convert, _parse_ts)
from hydra_etl.internal.connector.registry import build_connector

SLOT, PUB = "hydra_test_slot", "hydra_test_pub"


# ── Sans base ───────────────────────────────────────────────────────────────
@pytest.mark.parametrize("oid,text,expected", [
    (20, "9007199254740993", 9007199254740993),
    (1700, "10.25", decimal.Decimal("10.25")),
    (701, "0.5", 0.5),
    (16, "t", True),
    (1082, "2026-10-03", dt.date(2026, 10, 3)),
    (3802, '{"a": [1, 2]}', {"a": [1, 2]}),
    (25, "hello", "hello"),
    (2950, "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11", "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"),
])
def test_convert(oid, text, expected):
    assert _convert(oid, text) == expected


def test_parse_timestamps():
    assert _parse_ts("2026-11-09 18:39:57.9+00", tz=True) == dt.datetime(
        2026, 11, 9, 18, 39, 57, 900000, tzinfo=dt.timezone.utc)
    assert _parse_ts("2026-11-09 18:39:57.123456+05:30", tz=True).utcoffset() == dt.timedelta(hours=5, minutes=30)
    assert _parse_ts("2026-11-09 18:39:57", tz=False) == dt.datetime(2026, 11, 9, 18, 39, 57)


def test_config_is_checked():
    with pytest.raises(ValueError, match="connection.slot is required"):
        build_connector(name="c", config={"type": "postgresql_cdc", "connection": {
            "user": "u", "database": "d", "publication": "p"}})
    with pytest.raises(ValueError, match="lowercase letters"):
        build_connector(name="c", config={"type": "postgresql_cdc", "connection": {
            "user": "u", "database": "d", "publication": "p", "slot": "Bad-Slot"}})
    c = build_connector(name="c", config={"type": "postgres_cdc", "connection": {
        "user": "u", "database": "d", "publication": "p", "slot": "s"}})
    assert isinstance(c, PostgreSQLCDCConnector)
    with pytest.raises(ValueError, match="cannot be a destination"):
        c.begin_load(table="t")
    with pytest.raises(ValueError, match="not a query"):
        list(c.extract_batches(query="SELECT 1"))


def test_split_changes_keeps_the_final_state_per_key():
    from hydra_etl.internal.connector.postgresql_connector import PostgreSQLConnector
    pg = PostgreSQLConnector(name="pg", config={"type": "postgresql", "connection": {
        "user": "u", "database": "d"}})
    batch = [
        {"id": 1, "v": "a", "big": "x", "_op": "insert", "_lsn": "0/1", "_commit_time": None},
        {"id": 1, "v": "b", "big": UNCHANGED, "_op": "update", "_lsn": "0/2", "_commit_time": None},
        {"id": 2, "v": "c", "big": "y", "_op": "insert", "_lsn": "0/3", "_commit_time": None},
        {"id": 2, "v": None, "big": None, "_op": "delete", "_lsn": "0/4", "_commit_time": None},
        {"id": 3, "v": "d", "big": UNCHANGED, "_op": "update", "_lsn": "0/5", "_commit_time": None},
    ]
    upserts, changes = pg._split_changes(batch, ["id"])
    assert upserts == [{"id": 1, "v": "b", "big": "x"}]           # TOAST inchangé : valeur du lot
    assert changes["delete"] == [(2,)]
    assert changes["partial"] == [{"id": 3, "v": "d", "big": UNCHANGED}]


class _FakeCursor:
    """Curseur minimal : SHOW server_version_num puis la ligne de pg_replication_slots."""

    def __init__(self, version, row):
        self.version, self.row, self.sql = version, row, []

    def execute(self, sql, params=None):
        self.sql.append(sql)
        self._next = (str(self.version),) if sql.startswith("SHOW") else self.row

    def fetchone(self):
        return self._next


def _cdc(**conn):
    return PostgreSQLCDCConnector(name="c", config={"type": "postgresql_cdc", "connection": {
        "user": "u", "database": "d", "publication": "p", "slot": "s", **conn}})


MB = 1024 * 1024


def test_slot_check_is_quiet_under_the_threshold(caplog):
    cur = _FakeCursor(160000, (10 * MB, 5 * MB, "0/16B3748", False, "reserved", 5000 * MB))
    with caplog.at_level("WARNING"):
        st = _cdc().check_slot(cur)
    assert st["retained_bytes"] == 10 * MB and st["wal_status"] == "reserved"
    assert not caplog.records
    assert "wal_status, safe_wal_size" in cur.sql[-1]
    assert "invalidation_reason" not in cur.sql[-1]                 # colonne de PostgreSQL 17+


def test_slot_check_warns_on_lag_and_on_little_room_left(caplog):
    cur = _FakeCursor(170000, (2048 * MB, 2048 * MB, "0/1", False, "extended", 100 * MB, None))
    with caplog.at_level("WARNING"):
        _cdc(lag_warning_mb=1024).check_slot(cur)
    text = " | ".join(r.getMessage() for r in caplog.records)
    assert "retains 2,048.0 MB of WAL" in text
    assert "100.0 MB of WAL left before PostgreSQL invalidates it" in text


def test_slot_check_warns_on_unreserved(caplog):
    cur = _FakeCursor(150000, (5000 * MB, 5000 * MB, "0/1", False, "unreserved", -10 * MB))
    with caplog.at_level("WARNING"):
        _cdc().check_slot(cur)
    assert any("wal_status = unreserved" in r.getMessage() for r in caplog.records)


def test_slot_check_threshold_zero_never_warns(caplog):
    cur = _FakeCursor(160000, (99999 * MB, 99999 * MB, "0/1", False, "extended", 1))
    with caplog.at_level("WARNING"):
        _cdc(lag_warning_mb=0).check_slot(cur)
    assert not caplog.records


def test_slot_check_fails_on_an_invalidated_slot():
    cur = _FakeCursor(170000, (None, None, "0/2A0", False, "lost", None, "wal_removed"))
    with pytest.raises(ValueError) as e:
        _cdc().check_slot(cur)
    msg = str(e.value)
    assert "was invalidated" in msg and "reason: wal_removed" in msg
    assert "max_slot_wal_keep_size" in msg and "0/2A0" in msg
    assert "pg_drop_replication_slot('s')" in msg and "empty the destination table" in msg


def test_slot_check_before_postgresql_13_reads_retained_wal_only():
    cur = _FakeCursor(110005, (3 * MB, 1 * MB, "0/1", True))
    st = _cdc().check_slot(cur)
    assert st["wal_status"] is None and st["retained_bytes"] == 3 * MB
    assert "wal_status" not in cur.sql[-1]


def test_lag_warning_mb_is_checked():
    with pytest.raises(ValueError, match="lag_warning_mb must be a number"):
        _cdc(lag_warning_mb="beaucoup")
    with pytest.raises(ValueError, match="0 or more"):
        _cdc(lag_warning_mb=-1)
    assert _cdc(lag_warning_mb="512").lag_warning_mb == 512


def test_slot_conditions_are_part_of_the_language():
    from hydra_etl.workflow.conditions import parse_condition
    parse_condition("cdc.slot_status('orders') == 'lost' or cdc.slot_lag('orders') > 2GB")


def test_slot_probes_refuse_a_source_that_is_not_cdc(tmp_path):
    import yaml
    from hydra_etl.workflow.probes import ProbeContext, ProbeError, evaluate
    job = tmp_path / "jobs" / "j"
    job.mkdir(parents=True)
    (job / "sources.yaml").write_text(yaml.safe_dump({"version": "1.0", "sources": {"pg": {
        "type": "postgresql", "connection": {"user": "u", "database": "d"},
        "extract": {"table": "t"}}}}))
    with pytest.raises(ProbeError, match="not a postgresql_cdc source"):
        evaluate("cdc.slot_lag('pg') > 1MB", ProbeContext(root=tmp_path, workflow_jobs=[job]))


# ── Base réelle ─────────────────────────────────────────────────────────────
def _pg():
    raw = os.environ.get("HYDRA_TEST_PG")
    if not raw:
        pytest.skip("HYDRA_TEST_PG not set")
    cfg = dict(p.split("=", 1) for p in raw.split())
    import psycopg2
    conn = psycopg2.connect(host=cfg.get("host"), port=int(cfg.get("port", 5432)), user=cfg.get("user"),
                            password=cfg.get("password") or None, dbname=cfg.get("database"))
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SHOW wal_level")
    if cur.fetchone()[0] != "logical":
        conn.close()
        pytest.skip("wal_level is not logical")
    return cfg, conn, cur


def _reset(cur):
    cur.execute("SELECT pg_drop_replication_slot(slot_name) FROM pg_replication_slots WHERE slot_name = %s",
                (SLOT,))
    cur.execute(f"DROP PUBLICATION IF EXISTS {PUB}")
    cur.execute("DROP TABLE IF EXISTS cdc_src, cdc_mirror")


def _project(tmp_path: Path, cfg) -> Path:
    import yaml
    job = tmp_path / "jobs" / "mirror"
    job.mkdir(parents=True)
    conn = {k: v for k, v in cfg.items() if v}
    (job / "sources.yaml").write_text(yaml.safe_dump({"version": "1.0", "sources": {"changes": {
        "type": "postgresql_cdc", "connection": {**conn, "slot": SLOT, "publication": PUB},
        "extract": {"table": "public.cdc_src", "batch_size": 100}}}}))
    (job / "destinations.yaml").write_text(yaml.safe_dump({"version": "1.0", "destinations": {"mirror": {
        "type": "postgresql", "connection": conn,
        "load": {"table": "cdc_mirror", "mode": "upsert", "key": ["id"], "atomic": True}}}}))
    (job / "pipeline.yaml").write_text('version: "1.0"\npipeline:\n  from: changes\n  to: mirror\n')
    return job


def _run(job: Path):
    from hydra_etl.internal.runner.executor import JobExecutor
    return JobExecutor(job_dir=str(job)).run()


def _rows(cur, table):
    cur.execute(f"SELECT id, amount, doc, ts FROM {table} ORDER BY id")
    return cur.fetchall()


def test_mirror_follows_inserts_updates_deletes_and_survives_a_failed_load(tmp_path):
    cfg, conn, cur = _pg()
    try:
        _reset(cur)
        cur.execute("CREATE TABLE cdc_src (id bigint PRIMARY KEY, amount numeric(12,2), doc jsonb, ts timestamptz)")
        cur.execute("INSERT INTO cdc_src SELECT g, g * 1.25, jsonb_build_object('g', g), "
                    "'2026-10-01 09:00:00+02' FROM generate_series(1, 250) g")
        job = _project(tmp_path, cfg)

        # 1er run : slot créé, instantané de la table
        res = _run(job)
        assert res.success, res.error
        assert _rows(cur, "cdc_mirror") == _rows(cur, "cdc_src")
        cur.execute("SELECT data_type FROM information_schema.columns WHERE table_name = 'cdc_mirror' "
                    "ORDER BY ordinal_position")
        assert [r[0] for r in cur.fetchall()] == ["bigint", "numeric", "jsonb", "timestamp with time zone"]

        # 2e run : insert, update, delete (dont une clé insérée puis supprimée)
        cur.execute("INSERT INTO cdc_src VALUES (251, 1, '{\"new\": true}', now())")
        cur.execute("UPDATE cdc_src SET amount = amount + 100 WHERE id <= 120")
        cur.execute("DELETE FROM cdc_src WHERE id BETWEEN 200 AND 210")
        cur.execute("INSERT INTO cdc_src VALUES (252, 2, null, now())")
        cur.execute("DELETE FROM cdc_src WHERE id = 252")
        res = _run(job)
        assert res.success, res.error
        assert _rows(cur, "cdc_mirror") == _rows(cur, "cdc_src")

        # 3e run : la destination refuse un changement en plein chargement → rien n'est
        # publié, le slot n'avance pas ; une fois réparé, rien n'a été perdu
        cur.execute("ALTER TABLE cdc_mirror ADD CONSTRAINT small CHECK (amount < 10000)")
        cur.execute("UPDATE cdc_src SET amount = amount + 1 WHERE id <= 150")
        cur.execute("UPDATE cdc_src SET amount = 99999 WHERE id = 240")
        before = _rows(cur, "cdc_mirror")
        res = _run(job)
        assert not res.success
        assert _rows(cur, "cdc_mirror") == before            # tout ou rien
        cur.execute("ALTER TABLE cdc_mirror DROP CONSTRAINT small")
        res = _run(job)
        assert res.success, res.error
        assert _rows(cur, "cdc_mirror") == _rows(cur, "cdc_src")

        # 4e run : plus rien à lire
        res = _run(job)
        assert res.success and res.rows_in == 0
    finally:
        _reset(cur)
        conn.close()


def test_unchanged_toast_value_is_kept(tmp_path):
    cfg, conn, cur = _pg()
    try:
        _reset(cur)
        cur.execute("CREATE TABLE cdc_src (id bigint PRIMARY KEY, amount numeric(12,2), doc jsonb, ts timestamptz)")
        cur.execute("ALTER TABLE cdc_src ALTER COLUMN doc SET STORAGE EXTERNAL")   # TOAST sans compression
        big = '{"blob": "' + "z" * 20000 + '"}'
        cur.execute("INSERT INTO cdc_src VALUES (1, 1, %s, now())", (big,))
        job = _project(tmp_path, cfg)
        assert _run(job).success
        cur.execute("UPDATE cdc_src SET amount = 2 WHERE id = 1")             # doc non modifié : absent du journal
        res = _run(job)
        assert res.success, res.error
        assert _rows(cur, "cdc_mirror") == _rows(cur, "cdc_src")
    finally:
        _reset(cur)
        conn.close()


def test_cdc_source_refuses_workflow_rollback(tmp_path):
    from hydra_etl.internal.runner.executor import JobExecutor
    job = _project(tmp_path, {"host": "127.0.0.1", "port": "1", "user": "u", "database": "d"})
    res = JobExecutor(job_dir=str(job), undo=True).run()
    assert not res.success
    assert "cannot use rollback: true" in res.error


def test_invalidated_slot_makes_the_run_fail(tmp_path):
    """max_slot_wal_keep_size à 1 MB, du WAL généré, un CHECKPOINT : PostgreSQL 13+
    invalide le slot ; le run suivant doit échouer avec la marche à suivre."""
    cfg, conn, cur = _pg()
    cur.execute("SHOW server_version_num")
    if int(cur.fetchone()[0]) < 130000:
        conn.close()
        pytest.skip("max_slot_wal_keep_size needs PostgreSQL 13+")
    cur.execute("SHOW max_slot_wal_keep_size")
    keep = cur.fetchone()[0]
    try:
        _reset(cur)
        cur.execute("CREATE TABLE cdc_src (id bigint PRIMARY KEY, amount numeric(12,2), doc jsonb, ts timestamptz)")
        cur.execute("INSERT INTO cdc_src VALUES (1, 1, null, now())")
        job = _project(tmp_path, cfg)
        from hydra_etl.workflow.probes import ProbeContext, ProbeError, evaluate
        ctx = ProbeContext(root=tmp_path, workflow_jobs=[job])
        assert evaluate("cdc.slot_status('changes') == 'missing'", ctx).value
        assert evaluate("cdc.slot_lag('changes') == 0", ctx).value
        assert _run(job).success
        assert evaluate("cdc.slot_status('changes') == 'reserved'", ctx).value
        cur.execute("INSERT INTO cdc_src SELECT g, g, null, now() FROM generate_series(2, 20000) g")
        ev = evaluate("cdc.slot_lag('changes') > 100KB", ctx)
        assert ev.value and "MB of WAL kept" in ev.reason
        cur.execute("ALTER SYSTEM SET max_slot_wal_keep_size = '1MB'")
        cur.execute("SELECT pg_reload_conf()")
        for _ in range(6):                                    # plusieurs segments de WAL
            cur.execute("SELECT pg_switch_wal()")
            cur.execute("INSERT INTO cdc_src SELECT g, g, null, now() FROM generate_series(1000, 30000) g "
                        "ON CONFLICT (id) DO UPDATE SET amount = cdc_src.amount + 1")
            cur.execute("CHECKPOINT")
        cur.execute("SELECT wal_status FROM pg_replication_slots WHERE slot_name = %s", (SLOT,))
        assert cur.fetchone()[0] == "lost"
        res = _run(job)
        assert not res.success
        assert "was invalidated" in res.error and "pg_drop_replication_slot" in res.error
        assert evaluate("cdc.slot_status('changes') == 'lost' or cdc.slot_lag('changes') > 1GB", ctx).value
        with pytest.raises(ProbeError, match="invalidated"):
            evaluate("cdc.slot_lag('changes') > 1GB", ctx)
    finally:
        cur.execute(f"ALTER SYSTEM SET max_slot_wal_keep_size = '{keep}'")
        cur.execute("SELECT pg_reload_conf()")
        _reset(cur)
        conn.close()
