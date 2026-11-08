"""
Connecteur Snowflake — source en lecture seule.

    pip install "hydra-etl[snowflake]"

    sources:
      dwh:
        type: snowflake
        connection:
          account: ${SNOWFLAKE_ACCOUNT}       # ex. xy12345.eu-west-1
          user: ${SNOWFLAKE_USER}
          password: ${SNOWFLAKE_PASSWORD}     # ou private_key_file / authenticator
          warehouse: COMPUTE_WH
          database: SALES
          schema: PUBLIC
          role: ANALYST                       # facultatif
          column_case: lower                  # lower | preserve (défaut : preserve)
          json: parse                         # parse | text (défaut : parse)
        extract:
          table: ORDERS                       # ou query: "SELECT ..."

Ce que le connecteur garantit (les « pièges de types » d'une sortie de Snowflake) :

- NUMBER(p, 0) → entier Python exact, même au-delà de 64 bits (jamais de float) ;
- NUMBER(p, s>0) → Decimal exact (jamais de float) ;
- FLOAT → float ;
- DATE → date (pas un timestamp) ;
- TIMESTAMP_NTZ → datetime sans fuseau ; TIMESTAMP_TZ / TIMESTAMP_LTZ → datetime
  avec fuseau (l'instant est conservé) ;
- VARIANT / OBJECT / ARRAY → dict / list (json: parse) ou texte JSON (json: text) ;
- column_case: lower → noms de colonnes en minuscules (ce qu'attend PostgreSQL) ;
  deux colonnes qui ne diffèrent que par la casse sont refusées AVANT toute lecture.

Lecture : lots Arrow (`fetch_arrow_batches`) quand le pilote les fournit, sinon
`fetchmany` ; les deux chemins rendent exactement les mêmes valeurs Python.
Lecture seule : `query` doit être un SELECT (ou WITH / SHOW / DESCRIBE), et le
connecteur refuse d'être une destination.
"""

from __future__ import annotations

import datetime as _dt
import decimal
import json
import logging
import re
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence

from hydra_etl.internal.connector.interface import Batch, Connector

logger = logging.getLogger(__name__)

# Codes de type du pilote Snowflake (snowflake.connector.constants.FIELD_TYPES).
_FIXED = 0
_REAL = 1
_TEXT = 2
_DATE = 3
_TIMESTAMP = 4
_VARIANT = 5
_TIMESTAMP_LTZ = 6
_TIMESTAMP_TZ = 7
_TIMESTAMP_NTZ = 8
_OBJECT = 9
_ARRAY = 10
_BINARY = 11
_TIME = 12
_BOOLEAN = 13
_JSON_CODES = {_VARIANT, _OBJECT, _ARRAY}
_TYPE_NAMES = {
    _FIXED: "NUMBER", _REAL: "FLOAT", _TEXT: "TEXT", _DATE: "DATE", _TIMESTAMP: "TIMESTAMP",
    _VARIANT: "VARIANT", _TIMESTAMP_LTZ: "TIMESTAMP_LTZ", _TIMESTAMP_TZ: "TIMESTAMP_TZ",
    _TIMESTAMP_NTZ: "TIMESTAMP_NTZ", _OBJECT: "OBJECT", _ARRAY: "ARRAY", _BINARY: "BINARY",
    _TIME: "TIME", _BOOLEAN: "BOOLEAN",
}

_READ_ONLY_RE = re.compile(r"^\s*(\(|with\b|select\b|show\b|describe\b|desc\b)", re.IGNORECASE)
_IDENT = r'(?:[A-Za-z_][A-Za-z0-9_$]*|"(?:[^"]|"")+")'
_TABLE_RE = re.compile(rf"^{_IDENT}(?:\.{_IDENT}){{0,2}}$")

# Clés de `connection` transmises telles quelles à snowflake.connector.connect().
_CONNECT_KEYS = (
    "account", "user", "password", "authenticator", "token", "private_key_file",
    "private_key_file_pwd", "warehouse", "database", "schema", "role", "host", "port",
    "protocol", "login_timeout", "network_timeout", "client_session_keep_alive",
)


class _Column:
    __slots__ = ("source", "name", "code", "precision", "scale")

    def __init__(self, source: str, name: str, code: Optional[int],
                 precision: Optional[int], scale: Optional[int]) -> None:
        self.source, self.name, self.code = source, name, code
        self.precision, self.scale = precision, scale

    def describe(self) -> str:
        t = _TYPE_NAMES.get(self.code, f"type {self.code}")
        if self.code == _FIXED and self.precision is not None:
            t += f"({self.precision},{self.scale or 0})"
        return t


class SnowflakeConnector(Connector):
    """Source Snowflake (lecture seule)."""

    def __init__(self, name: str, config: Dict[str, Any]) -> None:
        super().__init__(name=name, config=config)
        conn = config.get("connection")
        if not isinstance(conn, dict):
            raise ValueError(f"SnowflakeConnector [{self.name}]: 'connection' must be a mapping")
        self._conn_cfg: Dict[str, Any] = dict(conn)
        missing = [k for k in ("account", "user") if not self._conn_cfg.get(k)]
        if missing:
            raise ValueError(f"SnowflakeConnector [{self.name}]: connection.{missing[0]} is required")
        case = str(self._conn_cfg.get("column_case") or "preserve").strip().lower()
        if case not in ("preserve", "lower"):
            raise ValueError(f"SnowflakeConnector [{self.name}]: connection.column_case must be "
                             f"'preserve' or 'lower' (got '{case}')")
        self.column_case = case
        js = str(self._conn_cfg.get("json") or "parse").strip().lower()
        if js not in ("parse", "text"):
            raise ValueError(f"SnowflakeConnector [{self.name}]: connection.json must be "
                             f"'parse' or 'text' (got '{js}')")
        self.json_mode = js
        self.arrow = bool(self._conn_cfg.get("arrow", True))

    # ── Connexion ────────────────────────────────────────────────────────
    def _connect(self):
        try:
            import snowflake.connector  # type: ignore
        except ImportError as e:
            raise ValueError(
                f"SnowflakeConnector [{self.name}]: the Snowflake driver is not installed. "
                f"Install it with 'pip install \"hydra-etl[snowflake]\"'.") from e
        kwargs = {k: self._conn_cfg[k] for k in _CONNECT_KEYS
                  if k in self._conn_cfg and self._conn_cfg[k] not in (None, "")}
        params = dict(self._conn_cfg.get("session_parameters") or {})
        params.setdefault("QUERY_TAG", "hydra-etl")
        kwargs["session_parameters"] = params
        import warnings
        try:
            with warnings.catch_warnings():
                # Avertissement du pilote sur un réglage de déconnexion, sans effet ici.
                warnings.filterwarnings("ignore", category=FutureWarning, module=r"snowflake\..*")
                return snowflake.connector.connect(**kwargs)
        except Exception as e:
            hint = ""
            if "404" in str(e) or "Not Found" in str(e):
                hint = (f"\n  Hint : Snowflake does not know the account '{self._conn_cfg.get('account')}'. "
                        f"Use the account identifier (ORGNAME-ACCOUNTNAME) or the locator with its region "
                        f"(for example xy12345.eu-central-2.aws), without https:// or .snowflakecomputing.com.")
            raise ValueError(
                f"SnowflakeConnector [{self.name}]: connection failed.\n"
                f"  DSN : {self._build_connection_string()}\n"
                f"  Error: {type(e).__name__}: {e}{hint}") from e

    def _build_connection_string(self) -> str:
        c = self._conn_cfg
        path = "/".join(str(c[k]) for k in ("database", "schema") if c.get(k))
        return f"snowflake://{c.get('user')}@{c.get('account')}/{path}"

    def test_connection(self) -> None:
        try:
            conn = self._connect()
            try:
                cur = conn.cursor()
                cur.execute("SELECT 1")
                cur.fetchone()
                cur.close()
            finally:
                conn.close()
        except Exception as e:
            raise ValueError(
                f"SnowflakeConnector [{self.name}]: connection test failed.\n"
                f"  DSN : {self._build_connection_string()}\n"
                f"  Error: {type(e).__name__}: {e}") from e

    # ── Lecture ──────────────────────────────────────────────────────────
    def _sql(self, query: Optional[str], table: Optional[str], limit: Optional[int]) -> str:
        if query and table:
            raise ValueError(f"SnowflakeConnector [{self.name}]: 'query' and 'table' are mutually exclusive")
        if not query and not table:
            raise ValueError(f"SnowflakeConnector [{self.name}]: 'query' or 'table' is required")
        if query:
            sql = query.strip().rstrip(";").strip()
            if not _READ_ONLY_RE.match(sql):
                raise ValueError(
                    f"SnowflakeConnector [{self.name}]: this source is read-only; extract.query must "
                    f"start with SELECT, WITH, SHOW or DESCRIBE")
        else:
            t = table.strip()
            if not _TABLE_RE.match(t):
                raise ValueError(
                    f"SnowflakeConnector [{self.name}]: invalid table name '{t}' (expected table, "
                    f"schema.table or database.schema.table; quote mixed-case names: \"MyTable\")")
            sql = f"SELECT * FROM {t}"
        if limit:
            sql = f"SELECT * FROM ({sql}) LIMIT {int(limit)}"
        return sql

    def _columns(self, description: Sequence[Any]) -> List[_Column]:
        cols: List[_Column] = []
        for d in description or []:
            name = getattr(d, "name", None) or d[0]
            code = getattr(d, "type_code", None) if hasattr(d, "type_code") else d[1]
            precision = getattr(d, "precision", None) if hasattr(d, "precision") else (d[4] if len(d) > 4 else None)
            scale = getattr(d, "scale", None) if hasattr(d, "scale") else (d[5] if len(d) > 5 else None)
            out = name.lower() if self.column_case == "lower" else name
            cols.append(_Column(name, out, code, precision, scale))
        seen: Dict[str, str] = {}
        for c in cols:
            key = c.name
            if key in seen:
                raise ValueError(
                    f"SnowflakeConnector [{self.name}]: columns '{seen[key]}' and '{c.source}' both "
                    f"become '{c.name}'" + (" with column_case: lower" if self.column_case == "lower" else "")
                    + ". Rename one of them in extract.query (AS ...) before loading.")
            seen[key] = c.source
        return cols

    def _log_types(self, cols: List[_Column]) -> None:
        notes = []
        for c in cols:
            if c.code == _FIXED and (c.scale or 0) == 0 and (c.precision or 0) > 18:
                notes.append(f"{c.name}: {c.describe()} kept as exact integers (may exceed 64 bits)")
            elif c.code == _FIXED and (c.scale or 0) > 0:
                notes.append(f"{c.name}: {c.describe()} kept as exact decimals")
            elif c.code in (_TIMESTAMP_TZ, _TIMESTAMP_LTZ):
                notes.append(f"{c.name}: {c.describe()} kept with its time zone")
            elif c.code in _JSON_CODES:
                notes.append(f"{c.name}: {c.describe()} read as "
                             + ("JSON values" if self.json_mode == "parse" else "JSON text"))
        if notes:
            logger.info("Snowflake source '%s': %s", self.name, "; ".join(notes))

    def _convert(self, col: _Column, v: Any) -> Any:
        if v is None:
            return None
        code = col.code
        if code == _FIXED:
            if isinstance(v, decimal.Decimal):
                if (col.scale or 0) == 0 and v == v.to_integral_value():
                    return int(v)
                return v
            if isinstance(v, float):                 # jamais attendu : on refuse de perdre en silence
                if (col.scale or 0) == 0 and v.is_integer() and abs(v) < 2 ** 53:
                    return int(v)
                return decimal.Decimal(repr(v))
            return v
        if code in _JSON_CODES:
            if self.json_mode == "parse":
                if isinstance(v, (bytes, bytearray)):
                    v = v.decode("utf-8")
                return json.loads(v) if isinstance(v, str) else v
            return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)
        if code == _DATE and isinstance(v, _dt.datetime):
            return v.date()
        if code == _TIMESTAMP_NTZ and isinstance(v, _dt.datetime) and v.tzinfo is not None:
            return v.replace(tzinfo=None)
        if hasattr(v, "to_pydatetime"):              # pandas.Timestamp (chemin Arrow)
            v = v.to_pydatetime()
        return v

    def _rows(self, cols: List[_Column], rows: Iterable[Sequence[Any]]) -> Batch:
        return [{c.name: self._convert(c, v) for c, v in zip(cols, r)} for r in rows]

    def _arrow_rows(self, cur, cols: List[_Column], batch_size: int) -> Iterator[Batch]:
        buf: Batch = []
        for table in cur.fetch_arrow_batches():
            names = table.column_names
            data = [table.column(n).to_pylist() for n in names]
            for i in range(table.num_rows):
                buf.append({c.name: self._convert(c, data[j][i]) for j, c in enumerate(cols)})
                if len(buf) >= batch_size:
                    yield buf
                    buf = []
        if buf:
            yield buf

    def extract_batches(self, *, query: Optional[str] = None, table: Optional[str] = None,
                        batch_size: int = 10_000,
                        incremental: Optional[Dict[str, Any]] = None) -> Iterator[Batch]:
        if incremental:
            raise ValueError(f"SnowflakeConnector [{self.name}]: incremental extraction is not supported yet")
        if not isinstance(batch_size, int) or batch_size < 1:
            raise ValueError(f"SnowflakeConnector [{self.name}]: 'batch_size' must be an integer >= 1")
        limit = (self.config.get("extract") or {}).get("limit")
        sql = self._sql(query, table, limit)
        conn = self._connect()
        try:
            cur = conn.cursor()
            try:
                cur.execute(sql)
                cols = self._columns(cur.description)
                self._log_types(cols)
                if self.arrow and callable(getattr(cur, "fetch_arrow_batches", None)):
                    yield from self._arrow_rows(cur, cols, batch_size)
                else:
                    while True:
                        rows = cur.fetchmany(batch_size)
                        if not rows:
                            break
                        yield self._rows(cols, rows)
            finally:
                try:
                    cur.close()
                except Exception:  # noqa: BLE001
                    pass
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass

    # ── Écriture : refusée ───────────────────────────────────────────────
    def load_batches(self, batches: Iterable[Batch], *, table: str, mode: str = "append",
                     key: Optional[List[str]] = None, **_: Any) -> None:
        raise ValueError(f"SnowflakeConnector [{self.name}]: Snowflake is a read-only source in "
                         f"Hydra ETL; it cannot be a destination")

    def begin_load(self, **_: Any):
        raise ValueError(f"SnowflakeConnector [{self.name}]: Snowflake is a read-only source in "
                         f"Hydra ETL; it cannot be a destination")
