"""Connecteur Snowflake (source en lecture seule), testé avec fakesnow
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


def test_cannot_be_a_destination():
    conn = _connector()
    with pytest.raises(ValueError, match="read-only source"):
        conn.load_batches([[{"a": 1}]], table="T")
    with pytest.raises(ValueError, match="read-only source"):
        conn.begin_load(table="T")


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
