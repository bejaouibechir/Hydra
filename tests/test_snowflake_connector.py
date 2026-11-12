"""Connecteur Snowflake (source et destination), testé avec fakesnow
(émulateur Snowflake sur DuckDB) et un faux curseur Arrow."""
from __future__ import annotations

import datetime as dt
import decimal

import pytest

from hydra_etl.internal.connector.registry import build_connector
from hydra_etl.internal.connector.snowflake_connector import SnowflakeConnector

fakesnow = pytest.importorskip("fakesnow")
pytest.importorskip("snowflake.connector")

CONN = {"account": "acme-test", "user": "hydra", "password": "x",
        "database": "SALES", "schema": "PUBLIC"}


@pytest.fixture()
def sf():
    with fakesnow.patch():
        import snowflake.connector as sc
        c = sc.connect(**{k: v for k, v in CONN.items()})
        cur = c.cursor()
        cur.execute("""create or replace table ORDERS (
            ID number(38,0), AMOUNT number(12,2), RATIO float, NAME varchar, OK boolean,
            D date, TS_NTZ timestamp_ntz, TS_TZ timestamp_tz, PAYLOAD variant,
            ATTRS object, TAGS array)""")
        cur.execute("""insert into ORDERS select 9007199254740993, 10.25, 0.5, 'a', true,
            '2026-01-31', '2026-01-31 10:00:00', '2026-01-31 10:00:00+02',
            parse_json('{"a": 1}'), object_construct('k', 'v'), array_construct(1, 2)""")
        cur.execute("insert into ORDERS (ID, NAME) values (2, null)")
        for i in range(3, 253):
            cur.execute(f"insert into ORDERS (ID, AMOUNT) values ({i}, {i}.5)")
        yield c
        c.close()


def _connector(**extra):
    return build_connector(name="dwh", config={"type": "snowflake",
                                               "connection": {**CONN, **extra}})


def _all(conn, **kw):
    return [r for b in conn.extract_batches(**kw) for r in b]


def test_registry_builds_snowflake():
    assert isinstance(_connector(), SnowflakeConnector)


def test_types_are_exact(sf):
    rows = _all(_connector(), query="select * from ORDERS order by ID desc", batch_size=1000)
    first = rows[0]
    assert first["ID"] == 9007199254740993 and type(first["ID"]) is int   # > 2**53 : pas de float
    assert first["AMOUNT"] == decimal.Decimal("10.25")
    assert isinstance(first["RATIO"], float)
    assert first["D"] == dt.date(2026, 1, 31) and not isinstance(first["D"], dt.datetime)
    assert first["TS_NTZ"] == dt.datetime(2026, 1, 31, 10, 0) and first["TS_NTZ"].tzinfo is None
    assert first["TS_TZ"].tzinfo is not None
    assert first["TS_TZ"] == dt.datetime(2026, 1, 31, 8, 0, tzinfo=dt.timezone.utc)
    assert first["PAYLOAD"] == {"a": 1}
    assert first["ATTRS"] == {"k": "v"}
    assert first["TAGS"] == [1, 2]
    assert first["OK"] is True


def test_json_text_mode(sf):
    rows = _all(_connector(json="text"), query="select PAYLOAD from ORDERS where ID = 9007199254740993")
    assert isinstance(rows[0]["PAYLOAD"], str) and '"a"' in rows[0]["PAYLOAD"]


def test_column_case_lower(sf):
    rows = _all(_connector(column_case="lower"), table="ORDERS", batch_size=1000)
    assert set(rows[0]) >= {"id", "amount", "ts_tz", "payload"}


def test_case_collision_refused_before_reading(sf):
    conn = _connector(column_case="lower")
    with pytest.raises(ValueError, match="both become 'id'"):
        _all(conn, query='select ID, ID as "id" from ORDERS')


def test_batches_respect_batch_size(sf):
    batches = list(_connector().extract_batches(table="ORDERS", batch_size=100))
    assert [len(b) for b in batches] == [100, 100, 52]


def test_nulls_stay_none(sf):
    rows = _all(_connector(), query="select * from ORDERS where ID = 2")
    assert rows[0]["NAME"] is None and rows[0]["AMOUNT"] is None and rows[0]["PAYLOAD"] is None


def test_limit_from_extract(sf):
    conn = build_connector(name="dwh", config={"type": "snowflake", "connection": CONN,
                                               "extract": {"table": "ORDERS", "limit": 5}})
    assert len(_all(conn, table="ORDERS")) == 5


def test_read_only_query_refused():
    with pytest.raises(ValueError, match="read-only"):
        _all(_connector(), query="delete from ORDERS")


def test_invalid_table_name_refused():
    with pytest.raises(ValueError, match="invalid table name"):
        _all(_connector(), table="ORDERS; drop table X")


def test_missing_account_refused():
    with pytest.raises(ValueError, match="connection.account is required"):
        build_connector(name="dwh", config={"type": "snowflake", "connection": {"user": "u"}})


def test_bad_options_refused():
    with pytest.raises(ValueError, match="column_case"):
        _connector(column_case="upper")
    with pytest.raises(ValueError, match="json must be"):
        _connector(json="yaml")


def test_connection_test(sf):
    _connector().test_connection()


# ── Chemin Arrow (fetch_arrow_batches du vrai pilote), simulé ──────────────
class _Desc(tuple):
    pass


def _desc(name, code, precision=None, scale=None):
    from collections import namedtuple
    D = namedtuple("D", "name type_code display_size internal_size precision scale is_nullable")
    return D(name, code, None, None, precision, scale, True)


class _ArrowCursor:
    def __init__(self, tables, description):
        self._tables, self.description = tables, description

    def execute(self, sql):
        self.sql = sql

    def fetch_arrow_batches(self):
        return iter(self._tables)

    def close(self):
        pass


class _ArrowConn:
    def __init__(self, cur):
        self._cur = cur

    def cursor(self):
        return self._cur

    def close(self):
        pass


def test_arrow_path_gives_same_values(monkeypatch):
    pa = pytest.importorskip("pyarrow")
    t1 = pa.table({
        "ID": pa.array([decimal.Decimal("12345678901234567890123")], pa.decimal128(38, 0)),
        "AMOUNT": pa.array([decimal.Decimal("10.25")], pa.decimal128(12, 2)),
        "D": pa.array([dt.date(2026, 1, 31)], pa.date32()),
        "TS_TZ": pa.array([dt.datetime(2026, 1, 31, 8, 0)], pa.timestamp("us", tz="UTC")),
        "PAYLOAD": pa.array(['{"a": [1, 2]}'], pa.string()),
    })
    t2 = pa.table({c: pa.array([None], t1.schema.field(c).type) for c in t1.column_names})
    desc = [_desc("ID", 0, 38, 0), _desc("AMOUNT", 0, 12, 2), _desc("D", 3),
            _desc("TS_TZ", 7), _desc("PAYLOAD", 5)]
    conn = _connector(column_case="lower")
    monkeypatch.setattr(conn, "_connect", lambda: _ArrowConn(_ArrowCursor([t1, t2], desc)))
    batches = list(conn.extract_batches(table="ORDERS", batch_size=1))
    assert len(batches) == 2
    row = batches[0][0]
    assert row["id"] == 12345678901234567890123 and type(row["id"]) is int  # au-delà de 64 bits
    assert row["amount"] == decimal.Decimal("10.25")
    assert row["d"] == dt.date(2026, 1, 31)
    assert row["ts_tz"].tzinfo is not None
    assert row["payload"] == {"a": [1, 2]}
    assert batches[1][0] == {"id": None, "amount": None, "d": None, "ts_tz": None, "payload": None}


def test_unknown_account_gets_a_hint(monkeypatch):
    import snowflake.connector as sc

    def boom(**_):
        raise sc.errors.DatabaseError("Failed to login: Snowflake responded with error status: 404 Not Found")
    monkeypatch.setattr(sc, "connect", boom)
    with pytest.raises(ValueError, match="does not know the account 'acme-test'"):
        _all(_connector(), table="ORDERS")


# ── Écriture (destination) ──────────────────────────────────────────────────

def _load(conn, batches, **kw):
    s = conn.begin_load(**kw)
    try:
        for b in batches:
            s.stage(b)
        s.publish()
    except BaseException:
        s.abort()
        raise
    return s


def _rows(sf, sql):
    cur = sf.cursor()
    cur.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def test_destination_creates_table_with_exact_types(sf):
    rows = [{"order_id": 9007199254740993, "amount": decimal.Decimal("10.25"), "ratio": 0.5,
             "name": "it's 100% \\ ok", "ok": True, "d": dt.date(2026, 1, 31),
             "ts": dt.datetime(2026, 1, 31, 10, 0, 0, 123456),
             "payload": {"a": [1, 2]}, "empty": None},
            {"order_id": 2, "amount": decimal.Decimal("3"), "ratio": 1.0, "name": None, "ok": False,
             "d": dt.date(2026, 2, 1), "ts": dt.datetime(2026, 2, 1), "payload": [1], "empty": None}]
    conn = _connector()
    _load(conn, [rows], table="OUT_ORDERS", mode="append")
    cur = sf.cursor()
    cur.execute("SELECT * FROM OUT_ORDERS LIMIT 0")
    names = [d.name for d in cur.description]
    assert names[:2] == ["ORDER_ID", "AMOUNT"]            # nom simple sans guillemets → majuscules
    back = sorted(_all(_connector(column_case="lower"), table="OUT_ORDERS"), key=lambda r: r["order_id"])
    assert back[1]["order_id"] == 9007199254740993 and isinstance(back[1]["order_id"], int)
    assert back[1]["amount"] == decimal.Decimal("10.25")
    assert back[0]["amount"] == decimal.Decimal("3")
    assert back[1]["ratio"] == 0.5 and back[1]["ok"] is True and back[0]["ok"] is False
    assert back[1]["name"] == "it's 100% \\ ok" and back[0]["name"] is None
    assert back[1]["d"] == dt.date(2026, 1, 31)
    assert back[1]["ts"] == dt.datetime(2026, 1, 31, 10, 0, 0, 123456)
    assert back[1]["payload"] == {"a": [1, 2]} and back[0]["payload"] == [1]
    assert back[1]["empty"] is None


def test_destination_append_matches_columns_without_case(sf):
    conn = _connector()
    _load(conn, [[{"ID": 300, "NAME": "x"}]], table="ORDERS", mode="append")
    _load(_connector(), [[{"id": 301, "Name": "y"}]], table="ORDERS", mode="append")
    got = _rows(sf, "SELECT ID, NAME FROM ORDERS WHERE ID BETWEEN 300 AND 400 ORDER BY ID")
    assert got == [{"ID": 300, "NAME": "x"}, {"ID": 301, "NAME": "y"}]


def test_destination_unknown_column_refused(sf):
    with pytest.raises(ValueError, match=r"column \['nope'\] not found in table ORDERS"):
        _load(_connector(), [[{"ID": 1, "nope": 2}]], table="ORDERS", mode="append")


def test_destination_columns_differing_by_case_refused(sf):
    with pytest.raises(ValueError, match="differ only by case"):
        _load(_connector(), [[{"id": 1, "ID": 2}]], table="NEW_T", mode="append")


def test_destination_replace_is_all_or_nothing(sf):
    _load(_connector(), [[{"k": 1, "v": "old"}, {"k": 2, "v": "old"}]], table="REP", mode="append")
    with pytest.raises(ValueError):
        _load(_connector(), [[{"k": 3, "v": "new"}], [{"k": "not a number", "v": "bad"}]],
              table="REP", mode="replace", atomic=True)
    assert _rows(sf, "SELECT K, V FROM REP ORDER BY K") == [{"K": 1, "V": "old"}, {"K": 2, "V": "old"}]
    _load(_connector(), [[{"k": 3, "v": "new"}]], table="REP", mode="replace", atomic=True)
    assert _rows(sf, "SELECT K, V FROM REP ORDER BY K") == [{"K": 3, "V": "new"}]


def test_destination_failed_atomic_load_drops_the_table_it_created(sf):
    with pytest.raises(ValueError):
        _load(_connector(), [[{"k": 1}], [{"k": "not a number"}]], table="FRESH", mode="append", atomic=True)
    cur = sf.cursor()
    with pytest.raises(Exception):
        cur.execute("SELECT * FROM FRESH LIMIT 0")


def test_destination_upsert(sf):
    _load(_connector(), [[{"id": 1, "v": "a"}, {"id": 2, "v": "b"}]], table="UPS", mode="upsert", key=["id"])
    _load(_connector(), [[{"id": 2, "v": "B"}, {"id": 3, "v": "c"}, {"id": 3, "v": "C"}]],
          table="UPS", mode="upsert", key=["id"])
    assert _rows(sf, "SELECT ID, V FROM UPS ORDER BY ID") == [
        {"ID": 1, "V": "a"}, {"ID": 2, "V": "B"}, {"ID": 3, "V": "C"}]


def test_destination_upsert_null_key_refused(sf):
    with pytest.raises(ValueError, match="no value for the upsert key"):
        _load(_connector(), [[{"id": None, "v": "a"}]], table="UPS2", mode="upsert", key=["id"])


def test_destination_upsert_needs_key():
    with pytest.raises(ValueError, match="needs load.key"):
        _connector().begin_load(table="T", mode="upsert")


def test_destination_bad_mode_and_table():
    with pytest.raises(ValueError, match="not supported"):
        _connector().begin_load(table="T", mode="merge")
    with pytest.raises(ValueError, match="invalid table name"):
        _connector().begin_load(table="T; drop table X", mode="append")


def test_destination_cdc_changes(sf):
    _load(_connector(), [[{"id": 1, "v": "a"}, {"id": 2, "v": "b"}]], table="MIRROR", mode="upsert", key=["id"])
    batch = [{"_op": "update", "id": 1, "v": "A"}, {"_op": "delete", "id": 2, "v": None},
             {"_op": "insert", "id": 3, "v": "c"}]
    _load(_connector(), [batch], table="MIRROR", mode="upsert", key=["id"])
    assert _rows(sf, "SELECT ID, V FROM MIRROR ORDER BY ID") == [{"ID": 1, "V": "A"}, {"ID": 3, "V": "c"}]


def test_destination_small_statements(sf, monkeypatch):
    monkeypatch.setattr(SnowflakeConnector, "_ROWS_PER_STATEMENT", 7)
    rows = [{"id": i, "v": f"r{i}"} for i in range(50)]
    _load(_connector(), [rows], table="MANY", mode="append")
    _load(_connector(), [rows], table="MANY", mode="upsert", key=["id"])
    assert _rows(sf, "SELECT COUNT(*) AS N FROM MANY") == [{"N": 50}]


def test_destination_pandas_values(sf):
    pd = pytest.importorskip("pandas")
    np = pytest.importorskip("numpy")
    rows = [{"i": np.int64(5), "f": float("nan"), "t": pd.Timestamp("2026-03-01 12:00:00")},
            {"i": np.int64(6), "f": np.float64(1.5), "t": pd.NaT}]
    _load(_connector(), [rows], table="PD", mode="append")
    assert _rows(sf, "SELECT I, F, T FROM PD ORDER BY I") == [
        {"I": 5, "F": None, "T": dt.datetime(2026, 3, 1, 12, 0)}, {"I": 6, "F": 1.5, "T": None}]


def test_destination_undo_replace(sf):
    _load(_connector(), [[{"k": 1, "v": "old"}]], table="UNDO_R", mode="append")
    conn = _connector()
    s = conn.begin_load(table="UNDO_R", mode="replace", atomic=True, undo=True)
    s.stage([{"k": 2, "v": "new"}])
    s.publish()
    assert _rows(sf, "SELECT K, V FROM UNDO_R") == [{"K": 2, "V": "new"}]
    msg = _connector()._undo_load(s.undo_record)
    assert "restored" in msg
    assert _rows(sf, "SELECT K, V FROM UNDO_R") == [{"K": 1, "V": "old"}]


def test_destination_undo_upsert(sf):
    _load(_connector(), [[{"id": 1, "v": "a"}]], table="UNDO_U", mode="upsert", key=["id"])
    conn = _connector()
    s = conn.begin_load(table="UNDO_U", mode="upsert", key=["id"], atomic=True, undo=True)
    s.stage([{"id": 1, "v": "A"}, {"id": 2, "v": "b"}])
    s.publish()
    _connector()._undo_load(s.undo_record)
    assert _rows(sf, "SELECT ID, V FROM UNDO_U ORDER BY ID") == [{"ID": 1, "V": "a"}]


def test_destination_through_open_load_session(sf):
    from hydra_etl.internal.connector.load_session import open_load_session, resolve_atomic
    conn = _connector()
    atomic, _ = resolve_atomic(conn, "replace", None)
    assert atomic is True
    s = open_load_session(conn, table="SESS", mode="replace", key=None, atomic=atomic)
    s.stage([{"a": 1}])
    s.publish()
    assert _rows(sf, "SELECT A FROM SESS") == [{"A": 1}]
