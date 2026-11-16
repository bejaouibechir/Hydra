"""Connecteur BigQuery (source et destination), testé avec un faux client qui
exécute le SQL BigQuery sur DuckDB (traduction sqlglot). Le test réel sur un
projet Google Cloud reste à faire."""
from __future__ import annotations

import datetime as dt
import decimal
import re
from types import SimpleNamespace

import pytest

bigquery = pytest.importorskip("google.cloud.bigquery")
duckdb = pytest.importorskip("duckdb")
sqlglot = pytest.importorskip("sqlglot")

from hydra_etl.internal.connector.bigquery_connector import BigQueryConnector  # noqa: E402
from hydra_etl.internal.connector.registry import build_connector  # noqa: E402

_TO_BQ = {"BIGINT": "INT64", "DOUBLE": "FLOAT64", "BOOLEAN": "BOOL", "VARCHAR": "STRING", "DATE": "DATE",
          "TIMESTAMP": "DATETIME", "TIMESTAMP WITH TIME ZONE": "TIMESTAMP", "JSON": "JSON", "BLOB": "BYTES",
          "TIME": "TIME"}
_TO_DUCK = {"INT64": "BIGINT", "STRING": "VARCHAR"}


class _Row(dict):
    pass


class _Result(list):
    schema: list = []


class _Job:
    def __init__(self, result):
        self._r = result

    def result(self, page_size=None, timeout=None):
        return self._r


class FakeBigQuery:
    """Sous-ensemble de google.cloud.bigquery.Client, sur DuckDB."""

    def __init__(self):
        self.db = duckdb.connect()
        self.queries: list = []

    @staticmethod
    def _parts(ref):
        ref = str(ref).strip("`")
        p = ref.split(".")
        return p[-2], p[-1]

    def _t(self, ref):
        ds, t = self._parts(ref)
        self.db.execute(f'CREATE SCHEMA IF NOT EXISTS "{ds}"')
        return f'"{ds}"."{t}"'

    def get_table(self, ref):
        from google.api_core.exceptions import NotFound
        ds, t = self._parts(ref)
        rows = self.db.execute("SELECT column_name, data_type FROM information_schema.columns "
                               "WHERE table_schema = ? AND table_name = ? ORDER BY ordinal_position",
                               [ds, t]).fetchall()
        if not rows:
            raise NotFound(f"table {ref}")
        def bq(dt_):
            return "NUMERIC" if dt_.startswith("DECIMAL") else _TO_BQ.get(dt_, dt_)
        return SimpleNamespace(schema=[SimpleNamespace(name=n, field_type=bq(d), mode="NULLABLE")
                                       for n, d in rows])

    def create_table(self, table, exists_ok=False):
        cols = ", ".join(f'"{f.name}" {_TO_DUCK.get(f.field_type, f.field_type)}' for f in table.schema)
        self.db.execute(f"CREATE TABLE {self._t(table.dataset_id + '.' + table.table_id)} ({cols})")

    def delete_table(self, ref, not_found_ok=False):
        self.db.execute(f"DROP TABLE IF EXISTS {self._t(ref)}")

    def load_table_from_json(self, rows, ref, job_config=None):
        if rows:
            cols = list(rows[0].keys())
            self.db.executemany(
                f"INSERT INTO {self._t(ref)} ({', '.join(chr(34) + c + chr(34) for c in cols)}) "
                f"VALUES ({', '.join('?' for _ in cols)})", [[r[c] for c in cols] for r in rows])
        return _Job(None)

    def query(self, sql, job_config=None):
        self.queries.append(sql)
        sql = re.sub(r"`[A-Za-z0-9_\-]+\.([A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+)`", r"`\1`", sql)
        res = _Result()
        try:
            for st in sqlglot.transpile(sql, read="bigquery", write="duckdb"):
                st = st.replace("AS DECIMAL)", "AS DECIMAL(38, 9))")
                cur = self.db.execute(st)
                if cur.description:
                    names = [d[0] for d in cur.description]
                    res = _Result(_Row(zip(names, r)) for r in cur.fetchall())
        except Exception:
            try:
                self.db.execute("ROLLBACK")          # BigQuery annule la transaction d'un script en échec
            except Exception:
                pass
            raise
        return _Job(res)


def _duckdb_has_merge() -> bool:
    con = duckdb.connect()
    try:
        con.execute("CREATE TABLE t (a INT)")
        con.execute("MERGE INTO t USING (SELECT 1 AS a) s ON t.a = s.a WHEN NOT MATCHED THEN INSERT VALUES (s.a)")
        return True
    except Exception:  # noqa: BLE001 - DuckDB < 1.4 (seule version pour Python 3.9)
        return False
    finally:
        con.close()


needs_merge = pytest.mark.skipif(not _duckdb_has_merge(),
                                 reason="this DuckDB has no MERGE (the fake client runs the SQL on DuckDB)")


@pytest.fixture()
def bq(monkeypatch):
    fake = FakeBigQuery()
    monkeypatch.setattr(BigQueryConnector, "_make_client", lambda self: fake)
    return fake


def _connector(**extra):
    return build_connector(name="bq", config={"type": "bigquery", "connection": {
        "project": "my-project", "dataset": "sales", **extra}})


def _load(batches, **kw):
    s = _connector().begin_load(**kw)
    try:
        for b in batches:
            s.stage(b)
        s.publish()
    except BaseException:
        s.abort()
        raise
    return s


def _rows(bq, sql):
    return [dict(r) for r in bq.query(sql).result()]


def _tables(bq):
    return {r[0] for r in bq.db.execute("SELECT table_name FROM information_schema.tables").fetchall()}


def test_registry_builds_bigquery():
    assert isinstance(_connector(), BigQueryConnector)


def test_connection_checks():
    with pytest.raises(ValueError, match="connection.project is required"):
        build_connector(name="bq", config={"type": "bigquery", "connection": {}})
    with pytest.raises(ValueError, match="invalid table name"):
        _connector(dataset=None).begin_load(table="orders", mode="append")
    with pytest.raises(ValueError, match="invalid table name"):
        _connector().begin_load(table="orders; drop", mode="append")
    with pytest.raises(ValueError, match="needs load.key"):
        _connector().begin_load(table="t", mode="upsert")
    with pytest.raises(ValueError, match="not supported"):
        _connector().begin_load(table="t", mode="merge")


def test_rollback_not_available(bq):
    from hydra_etl.internal.connector.undo import UndoUnavailable
    with pytest.raises(UndoUnavailable):
        _connector().begin_load(table="t", mode="append", undo=True)


def test_creates_table_with_exact_types(bq):
    rows = [{"id": 9007199254740993, "amount": decimal.Decimal("10.25"), "ratio": 0.5, "name": "it's 100%",
             "ok": True, "d": dt.date(2026, 1, 31), "ts": dt.datetime(2026, 1, 31, 10, 0, 0, 123456),
             "payload": {"a": [1, 2]}, "empty": None},
            {"id": 2, "amount": decimal.Decimal("3"), "ratio": 1.0, "name": None, "ok": False,
             "d": dt.date(2026, 2, 1), "ts": dt.datetime(2026, 2, 1), "payload": [1], "empty": None}]
    _load([rows], table="orders", mode="append")
    types = {f.name: f.field_type for f in bq.get_table("my-project.sales.orders").schema}
    assert types["id"] == "INT64" and types["amount"] == "NUMERIC" and types["ratio"] == "FLOAT64"
    assert types["ok"] == "BOOL" and types["d"] == "DATE" and types["ts"] == "DATETIME"
    assert types["payload"] == "JSON" and types["empty"] == "STRING"
    back = sorted((r for b in _connector().extract_batches(table="orders") for r in b), key=lambda r: r["id"])
    assert back[1]["id"] == 9007199254740993
    assert back[1]["amount"] == decimal.Decimal("10.25") and back[0]["amount"] == decimal.Decimal("3")
    assert back[1]["name"] == "it's 100%" and back[0]["name"] is None
    assert back[1]["ts"] == dt.datetime(2026, 1, 31, 10, 0, 0, 123456)
    assert not any(t.startswith("_hydra_stage_") for t in _tables(bq))        # transit supprimé


def test_append_matches_columns_without_case(bq):
    _load([[{"ID": 1, "Name": "x"}]], table="orders", mode="append")
    _load([[{"id": 2, "name": "y"}]], table="orders", mode="append")
    assert _rows(bq, "SELECT * FROM `my-project.sales.orders` ORDER BY ID") == [
        {"ID": 1, "Name": "x"}, {"ID": 2, "Name": "y"}]


def test_unknown_column_and_case_duplicates_refused(bq):
    _load([[{"id": 1}]], table="orders", mode="append")
    with pytest.raises(ValueError, match=r"column \['nope'\] not found in table my-project.sales.orders"):
        _load([[{"id": 2, "nope": 1}]], table="orders", mode="append")
    with pytest.raises(ValueError, match="differ only by case"):
        _load([[{"id": 1, "ID": 2}]], table="other", mode="append")


def test_nothing_visible_before_publish_and_abort_cleans_up(bq):
    _load([[{"k": 1, "v": "old"}]], table="rep", mode="append")
    s = _connector().begin_load(table="rep", mode="replace")
    s.stage([{"k": 2, "v": "new"}])
    assert _rows(bq, "SELECT k, v FROM `my-project.sales.rep`") == [{"k": 1, "v": "old"}]
    s.abort()
    assert _rows(bq, "SELECT k, v FROM `my-project.sales.rep`") == [{"k": 1, "v": "old"}]
    assert not any(t.startswith("_hydra_stage_") for t in _tables(bq))


def test_replace_and_bad_value(bq):
    _load([[{"k": 1, "v": "old"}, {"k": 2, "v": "old"}]], table="rep", mode="append")
    with pytest.raises(ValueError):
        _load([[{"k": 3, "v": "new"}], [{"k": "not a number", "v": "bad"}]], table="rep", mode="replace")
    assert _rows(bq, "SELECT k, v FROM `my-project.sales.rep` ORDER BY k") == [
        {"k": 1, "v": "old"}, {"k": 2, "v": "old"}]
    _load([[{"k": 3, "v": "new"}]], table="rep", mode="replace")
    assert _rows(bq, "SELECT k, v FROM `my-project.sales.rep`") == [{"k": 3, "v": "new"}]
    assert any("BEGIN TRANSACTION" in q for q in bq.queries)


@needs_merge
def test_upsert(bq):
    _load([[{"id": 1, "v": "a"}, {"id": 2, "v": "b"}]], table="ups", mode="upsert", key=["id"])
    _load([[{"id": 2, "v": "B"}, {"id": 3, "v": "c"}], [{"id": 3, "v": "C"}]],
          table="ups", mode="upsert", key=["id"])
    assert _rows(bq, "SELECT id, v FROM `my-project.sales.ups` ORDER BY id") == [
        {"id": 1, "v": "a"}, {"id": 2, "v": "B"}, {"id": 3, "v": "C"}]
    assert any(q.startswith("MERGE") for q in bq.queries)


def test_upsert_null_key_refused(bq):
    with pytest.raises(ValueError, match="no value for the upsert key"):
        _load([[{"id": None, "v": "a"}]], table="ups", mode="upsert", key=["id"])


@needs_merge
def test_cdc_changes(bq):
    _load([[{"id": 1, "v": "a"}, {"id": 2, "v": "b"}]], table="mirror", mode="upsert", key=["id"])
    batch = [{"_op": "update", "id": 1, "v": "A"}, {"_op": "delete", "id": 2, "v": None},
             {"_op": "insert", "id": 3, "v": "c"}]
    _load([batch], table="mirror", mode="upsert", key=["id"])
    assert _rows(bq, "SELECT id, v FROM `my-project.sales.mirror` ORDER BY id") == [
        {"id": 1, "v": "A"}, {"id": 3, "v": "c"}]


def test_not_atomic_publishes_each_batch(bq):
    s = _connector().begin_load(table="each", mode="append", atomic=False)
    s.stage([{"a": 1}])
    assert _rows(bq, "SELECT a FROM `my-project.sales.each`") == [{"a": 1}]
    s.stage([{"a": 2}])
    s.publish()
    assert _rows(bq, "SELECT a FROM `my-project.sales.each` ORDER BY a") == [{"a": 1}, {"a": 2}]


def test_pandas_values(bq):
    pd = pytest.importorskip("pandas")
    np = pytest.importorskip("numpy")
    rows = [{"i": np.int64(5), "f": float("nan"), "t": pd.Timestamp("2026-03-01 12:00:00")},
            {"i": np.int64(6), "f": np.float64(1.5), "t": pd.NaT}]
    _load([rows], table="pd", mode="append")
    assert _rows(bq, "SELECT i, f, t FROM `my-project.sales.pd` ORDER BY i") == [
        {"i": 5, "f": None, "t": dt.datetime(2026, 3, 1, 12, 0)}, {"i": 6, "f": 1.5, "t": None}]


def test_source_query_must_read(bq):
    with pytest.raises(ValueError, match="must start with SELECT or WITH"):
        list(_connector().extract_batches(query="DELETE FROM x WHERE TRUE"))


def test_source_batches_and_limit(bq):
    _load([[{"id": i} for i in range(25)]], table="many", mode="append")
    batches = list(_connector().extract_batches(table="many", batch_size=10))
    assert [len(b) for b in batches] == [10, 10, 5]
    c = build_connector(name="bq", config={"type": "bigquery", "extract": {"limit": 3},
                                           "connection": {"project": "my-project", "dataset": "sales"}})
    assert sum(len(b) for b in c.extract_batches(table="many")) == 3


def test_through_open_load_session(bq):
    from hydra_etl.internal.connector.load_session import open_load_session, resolve_atomic
    conn = _connector()
    for mode in ("append", "replace", "upsert"):
        assert resolve_atomic(conn, mode, None) == (True, None)
    s = open_load_session(conn, table="sess", mode="replace", key=None, atomic=True)
    s.stage([{"a": 1}])
    s.publish()
    assert _rows(bq, "SELECT a FROM `my-project.sales.sess`") == [{"a": 1}]
