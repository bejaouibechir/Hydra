"""
Connecteur Snowflake — source et destination.

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

    destinations:
      dwh:
        type: snowflake
        connection: { account: ..., user: ..., warehouse: ..., database: ..., schema: ... }
        load:
          table: ORDERS                       # table, schema.table ou database.schema.table
          mode: upsert                        # append | replace | upsert
          key: [order_id]

Ce que le connecteur garantit en lecture (les « pièges de types » d'une sortie de Snowflake) :

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
`extract.query` doit être un SELECT (ou WITH / SHOW / DESCRIBE).

Écriture (même garantie, dans l'autre sens) :

- chaque valeur est envoyée en texte puis convertie par Snowflake dans le type
  de la colonne cible (NUMBER(p, s), FLOAT, DATE, TIMESTAMP_*, VARIANT, BINARY…) :
  aucun entier ni décimal ne passe par un float ;
- table absente : créée au premier lot, types déduits du lot (entiers → NUMBER(38,0),
  décimaux → NUMBER(38, s), datetime avec fuseau → TIMESTAMP_TZ, dict / list →
  VARIANT…) ; en upsert, la clé devient la clé primaire (informative chez Snowflake) ;
- noms de colonnes : rapprochés de ceux de la table sans tenir compte de la casse
  (règle de Snowflake pour les noms sans guillemets) ; deux colonnes du lot qui ne
  diffèrent que par la casse sont refusées ; une colonne absente de la table aussi ;
- replace : DELETE puis insertion dans la même transaction (tout ou rien par défaut) ;
- upsert : MERGE sur la clé ; une clé vide est refusée ; deux lignes de même clé
  dans un lot → la dernière l'emporte ; changements d'une source CDC (_op) : les
  suppressions sont appliquées ;
- Snowflake valide toute instruction DDL : une table créée par un chargement en
  tout ou rien qui échoue est supprimée.
"""

from __future__ import annotations

import datetime as _dt
import decimal
import json
import logging
import math
import re
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

from hydra_etl.internal.connector.base_db_connector import BaseDBConnector
from hydra_etl.internal.connector.interface import Batch

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


class SnowflakeConnector(BaseDBConnector):
    """Source et destination Snowflake."""

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
        # Transactions explicites : le chargement valide lui-même (tout ou rien).
        kwargs["autocommit"] = False
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

    # ── Écriture ─────────────────────────────────────────────────────────
    # Lignes par instruction INSERT / MERGE (VALUES accepte 16 384 lignes ;
    # le texte d'une instruction est aussi limité) et taille maximale du texte.
    _ROWS_PER_STATEMENT = 1000
    _MAX_STATEMENT_CHARS = 800_000
    _CDC_COLUMNS = ("_op", "_lsn", "_commit_time")
    _wrap_load_value_errors = False

    def _build_columns_query(self, table: str) -> str:
        return f"SELECT * FROM {self._q_table(table)} LIMIT 0"

    def _check_load_args(self, table: str, mode: str, key: Optional[List[str]]):
        if not isinstance(table, str) or not table.strip():
            raise ValueError(f"SnowflakeConnector [{self.name}]: 'table' must be a non-empty name")
        table = self._q_table(table.strip())
        if mode not in ("append", "replace", "upsert"):
            raise ValueError(f"SnowflakeConnector [{self.name}]: mode '{mode}' is not supported. "
                             f"Supported: append, replace, upsert")
        if isinstance(key, str):
            key = [key]
        if mode == "upsert":
            if not key or not all(isinstance(k, str) and k.strip() for k in key):
                raise ValueError(f"SnowflakeConnector [{self.name}]: mode 'upsert' needs load.key "
                                 f"(the columns that identify a row)")
        if key:
            key = [k.strip() for k in key]
            for k in key:
                self._q_col(k)
        return table, key

    def _load_prepare(self, cur, *, table, mode, key, atomic, commit, **_):
        exists = self._table_exists(cur, table)
        ctx: Dict[str, Any] = {"table": table, "mode": mode, "key": key, "atomic": atomic,
                               "exists": exists, "created": False, "meta": None, "columns": None}
        if exists:
            ctx["meta"] = self._table_meta(cur, table)
            if mode == "upsert":
                self._resolve(ctx, key, what="upsert key")
            if mode == "replace":
                # DML : annulé avec le reste en tout ou rien (TRUNCATE validerait tout de suite)
                cur.execute(f"DELETE FROM {table}")
        return ctx

    def _load_write(self, cur, ctx, batch, *, commit):
        rows = [r for r in batch]
        if not rows:
            return
        deletes: List[tuple] = []
        if isinstance(rows[0], dict) and "_op" in rows[0]:
            rows, deletes = self._cdc_changes(rows, ctx)
        if rows and ctx["columns"] is None:
            first = rows[0]
            if not isinstance(first, dict) or not first:
                raise ValueError(f"SnowflakeConnector [{self.name}]: invalid batch (first row empty)")
            names = [c for c in first.keys() if isinstance(c, str) and c.strip()]
            seen: Dict[str, str] = {}
            for c in names:
                u = c.upper()
                if u in seen:
                    raise ValueError(
                        f"SnowflakeConnector [{self.name}]: columns '{seen[u]}' and '{c}' differ only by "
                        f"case; Snowflake would store them in the same column. Rename one of them "
                        f"(rename step) before loading.")
                seen[u] = c
            if not ctx["exists"]:
                self._create_table(cur, ctx, names, rows)
            ctx["targets"] = self._resolve(ctx, names, what="column")
            ctx["columns"] = names
        if rows:
            if ctx["mode"] == "upsert":
                self._merge(cur, ctx, self._last_per_key(rows, ctx))
            else:
                self._insert(cur, ctx, rows)
        if deletes and ctx["exists"]:
            kcols = [self._q_col(t[0]) for t in self._resolve(ctx, ctx["key"], what="upsert key")]
            for i in range(0, len(deletes), 500):
                chunk = deletes[i:i + 500]
                one = "(" + " AND ".join(f"{c} = %s" for c in kcols) + ")"
                cur.execute(f"DELETE FROM {ctx['table']} WHERE " + " OR ".join([one] * len(chunk)),
                            [_sf_text(v, None) for k in chunk for v in k])

    def _load_aborted(self, ctx: Dict[str, Any]) -> None:
        # CREATE TABLE est validé tout de suite par Snowflake : en tout ou rien,
        # la table créée par ce chargement ne doit pas survivre à l'échec.
        if ctx.get("created") and ctx.get("atomic"):
            conn = self._connect()
            try:
                cur = conn.cursor()
                cur.execute(f"DROP TABLE IF EXISTS {ctx['table']}")
                conn.commit()
            finally:
                conn.close()

    # ── Table cible ──
    def _table_meta(self, cur, table: str) -> List[Tuple[str, Optional[int], Optional[int], Optional[int]]]:
        cur.execute(self._build_columns_query(table))
        try:
            cur.fetchall()
        except Exception:  # noqa: BLE001
            pass
        out = []
        for d in cur.description or []:
            name = getattr(d, "name", None) or d[0]
            code = getattr(d, "type_code", None) if hasattr(d, "type_code") else d[1]
            precision = getattr(d, "precision", None) if hasattr(d, "precision") else (d[4] if len(d) > 4 else None)
            scale = getattr(d, "scale", None) if hasattr(d, "scale") else (d[5] if len(d) > 5 else None)
            out.append((name, code, precision, scale))
        self._colmap = {m[0].upper(): m[0] for m in out}
        self._colexact = {m[0] for m in out}
        return out

    def _resolve(self, ctx, names: List[str], *, what: str) -> List[Tuple[str, Optional[int], Optional[int], Optional[int]]]:
        """Colonnes de la table pour ces noms (sans tenir compte de la casse)."""
        by_upper = {m[0].upper(): m for m in ctx["meta"]}
        exact = {m[0]: m for m in ctx["meta"]}
        out, missing = [], []
        for n in names:
            m = exact.get(n) or by_upper.get(n.upper())
            if m is None:
                missing.append(n)
            else:
                out.append(m)
        if missing:
            have = ", ".join(m[0] for m in ctx["meta"])
            raise ValueError(
                f"SnowflakeConnector [{self.name}]: {what} {missing} not found in table "
                f"{ctx['table']} (columns: {have}). Add the column to the table, or rename or drop it "
                f"before loading.")
        return out

    def _create_table(self, cur, ctx, names: List[str], rows: List[Dict[str, Any]]) -> None:
        defs = []
        for c in names:
            defs.append(f"{self._new_col(c)} {self._sf_type(c, [_sf_norm(r.get(c)) for r in rows])}")
        if ctx["mode"] == "upsert":
            missing = [k for k in ctx["key"] if k not in names]
            if missing:
                raise ValueError(f"SnowflakeConnector [{self.name}]: upsert key {missing} is not in the "
                                 f"data (columns: {names})")
            defs.append(f"PRIMARY KEY ({', '.join(self._new_col(k) for k in ctx['key'])})")
        cur.execute(f"CREATE TABLE {ctx['table']} ({', '.join(defs)})")
        ctx["exists"] = ctx["created"] = True
        ctx["meta"] = self._table_meta(cur, ctx["table"])
        logger.info("Snowflake destination '%s': table %s created (%s)", self.name, ctx["table"],
                    ", ".join(defs))

    def _sf_type(self, column: str, values: List[Any]) -> str:
        """Type Snowflake fidèle aux valeurs d'une colonne (création de table)."""
        vals = [v for v in values if v is not None]
        if not vals:
            return "VARCHAR"
        if all(isinstance(v, bool) for v in vals):
            return "BOOLEAN"
        if all(isinstance(v, (int, decimal.Decimal)) and not isinstance(v, bool) for v in vals):
            scale = 0
            digits = 0
            for v in vals:
                t = decimal.Decimal(v).as_tuple()
                s = max(0, -t.exponent) if isinstance(t.exponent, int) else 0
                scale = max(scale, s)
                digits = max(digits, len(t.digits) + (t.exponent if isinstance(t.exponent, int) and t.exponent > 0 else 0) - s)
            if scale > 37 or digits + scale > 38:
                raise ValueError(
                    f"SnowflakeConnector [{self.name}]: column '{column}' holds numbers that do not fit "
                    f"in NUMBER(38, s) ({digits} digits before the point, {scale} after). Cast it to str "
                    f"(cast step) to load it as text, or create the table yourself.")
            return f"NUMBER(38,{scale})"
        if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals):
            return "FLOAT"
        if all(isinstance(v, _dt.datetime) for v in vals):
            return "TIMESTAMP_TZ" if all(v.tzinfo is not None for v in vals) else "TIMESTAMP_NTZ"
        if all(isinstance(v, _dt.date) and not isinstance(v, _dt.datetime) for v in vals):
            return "DATE"
        if all(isinstance(v, _dt.date) for v in vals):
            return "TIMESTAMP_NTZ"
        if all(isinstance(v, _dt.time) for v in vals):
            return "TIME"
        if all(isinstance(v, (dict, list)) for v in vals):
            return "VARIANT"
        if all(isinstance(v, (bytes, bytearray)) for v in vals):
            return "BINARY"
        return "VARCHAR"

    # ── Instructions ──
    @staticmethod
    def _cast(alias: str, code: Optional[int], precision: Optional[int], scale: Optional[int]) -> str:
        if code == _FIXED:
            return f"{alias}::NUMBER({precision or 38},{scale or 0})"
        if code == _REAL:
            return f"{alias}::FLOAT"
        if code == _BOOLEAN:
            return f"{alias}::BOOLEAN"
        if code == _DATE:
            return f"{alias}::DATE"
        if code == _TIME:
            return f"{alias}::TIME"
        if code in (_TIMESTAMP_NTZ, _TIMESTAMP):
            return f"{alias}::TIMESTAMP_NTZ"
        if code == _TIMESTAMP_TZ:
            return f"{alias}::TIMESTAMP_TZ"
        if code == _TIMESTAMP_LTZ:
            return f"{alias}::TIMESTAMP_LTZ"
        if code == _OBJECT:
            return f"PARSE_JSON({alias})::OBJECT"
        if code == _ARRAY:
            return f"PARSE_JSON({alias})::ARRAY"
        if code == _VARIANT:
            return f"PARSE_JSON({alias})"
        if code == _BINARY:
            return f"TO_BINARY({alias}, 'HEX')"
        return f"{alias}::VARCHAR"

    def _chunks(self, rows: List[Dict[str, Any]], cols: List[str], targets) -> Iterator[Tuple[int, List[Any]]]:
        """(nombre de lignes, valeurs texte à plat) par instruction."""
        params: List[Any] = []
        n = size = 0
        for r in rows:
            vals = [_sf_text(_sf_norm(r.get(c)), t[1]) for c, t in zip(cols, targets)]
            params.extend(vals)
            n += 1
            size += sum(len(v) + 4 if v is not None else 6 for v in vals)
            if n >= self._ROWS_PER_STATEMENT or size >= self._MAX_STATEMENT_CHARS:
                yield n, params
                params, n, size = [], 0, 0
        if n:
            yield n, params

    def _source_sql(self, cols: List[str], targets, n: int) -> str:
        aliases = [f"c{i}" for i in range(len(cols))]
        exprs = ", ".join(f"{self._cast(a, t[1], t[2], t[3])} AS {self._q_col(t[0])}"
                          for a, t in zip(aliases, targets))
        ph = "(" + ", ".join(["%s"] * len(cols)) + ")"
        return f"SELECT {exprs} FROM VALUES {', '.join([ph] * n)} AS v ({', '.join(aliases)})"

    def _insert(self, cur, ctx, rows: List[Dict[str, Any]]) -> None:
        cols, targets = ctx["columns"], ctx["targets"]
        col_sql = ", ".join(self._q_col(t[0]) for t in targets)
        for n, params in self._chunks(rows, cols, targets):
            cur.execute(f"INSERT INTO {ctx['table']} ({col_sql}) {self._source_sql(cols, targets, n)}", params)

    def _merge(self, cur, ctx, rows: List[Dict[str, Any]]) -> None:
        cols, targets = ctx["columns"], ctx["targets"]
        keys = {t[0] for t in self._resolve(ctx, ctx["key"], what="upsert key")}
        missing = [k for k in ctx["key"] if k not in cols]
        if missing:
            raise ValueError(f"SnowflakeConnector [{self.name}]: upsert key {missing} is not in the data "
                             f"(columns: {cols})")
        on = " AND ".join(f"t.{self._q_col(k)} = s.{self._q_col(k)}" for k in sorted(keys))
        upd = [t[0] for t in targets if t[0] not in keys]
        ins = ", ".join(self._q_col(t[0]) for t in targets)
        ins_v = ", ".join(f"s.{self._q_col(t[0])}" for t in targets)
        when = (" WHEN MATCHED THEN UPDATE SET "
                + ", ".join(f"t.{self._q_col(c)} = s.{self._q_col(c)}" for c in upd)) if upd else ""
        for n, params in self._chunks(rows, cols, targets):
            cur.execute(f"MERGE INTO {ctx['table']} t USING ({self._source_sql(cols, targets, n)}) s "
                        f"ON {on}{when} WHEN NOT MATCHED THEN INSERT ({ins}) VALUES ({ins_v})", params)

    def _last_per_key(self, rows: List[Dict[str, Any]], ctx) -> List[Dict[str, Any]]:
        """Une ligne par clé (la dernière l'emporte, comme une suite d'upserts) ; clé vide refusée
        (MERGE ne la retrouverait jamais et l'ajouterait à chaque chargement)."""
        key = ctx["key"]
        final: Dict[tuple, Dict[str, Any]] = {}
        for r in rows:
            k = tuple(_sf_norm(r.get(c)) for c in key)
            if any(v is None for v in k):
                raise ValueError(f"SnowflakeConnector [{self.name}]: a row has no value for the upsert "
                                 f"key {list(key)}: {dict(zip(key, k))}")
            final.pop(k, None)
            final[k] = r
        return list(final.values())

    def _cdc_changes(self, rows: List[Dict[str, Any]], ctx) -> Tuple[List[Dict[str, Any]], List[tuple]]:
        """Lot d'une source CDC : état final de chaque clé ; lignes à écrire et clés à supprimer."""
        if ctx["mode"] != "upsert":
            raise ValueError(f"SnowflakeConnector [{self.name}]: changes from a CDC source need "
                             f"mode: upsert with load.key")
        from hydra_etl.internal.connector.postgresql_connector import PostgreSQLConnector
        upserts, changes = PostgreSQLConnector._split_changes(self, rows, ctx["key"])
        if changes["partial"]:
            raise ValueError(
                f"SnowflakeConnector [{self.name}]: {len(changes['partial'])} change(s) do not carry every "
                f"column (large values left unchanged by PostgreSQL). Set REPLICA IDENTITY FULL on the "
                f"source table so that each change carries the whole row.")
        return upserts, [tuple(_sf_norm(v) for v in k) for k in changes["delete"]]

    # ── Annulation (rollback d'un workflow, voir undo.py) ──
    def _q_table(self, table: str) -> str:
        t = (table or "").strip()
        if not _TABLE_RE.match(t) or "%" in t:
            raise ValueError(
                f"SnowflakeConnector [{self.name}]: invalid table name '{t}' (expected table, "
                f"schema.table or database.schema.table; quote mixed-case names: \"MyTable\")")
        return t

    def _q_col(self, column: str) -> str:
        """Colonne citée ; un nom connu de la table est pris tel que Snowflake le stocke
        (ORDER_ID pour order_id), sans tenir compte de la casse."""
        c = (column or "").strip()
        if not c or "%" in c:
            raise ValueError(f"SnowflakeConnector [{self.name}]: invalid column name {column!r}")
        if c not in getattr(self, "_colexact", ()):
            c = getattr(self, "_colmap", {}).get(c.upper(), c)
        return '"' + c.replace('"', '""') + '"'

    def _new_col(self, column: str) -> str:
        """Colonne d'une table créée : nom simple sans guillemets (stocké en majuscules,
        convention de Snowflake), sinon cité tel quel."""
        c = column.strip()
        if re.match(r"^[A-Za-z_][A-Za-z0-9_$]*$", c):
            return c
        return self._q_col(c)

    def _bak_ref(self, table: str, bak: str) -> str:
        parts = re.findall(rf"{_IDENT}", table)
        return ".".join(parts[:-1] + [bak]) if len(parts) > 1 else bak

    def _undo_begin(self, cur, table, mode, key):
        rec = super()._undo_begin(cur, table, mode, key)
        if not rec.created:
            self._table_meta(cur, table)            # noms réels des colonnes (pour _q_col)
        return rec

    def _undo_load(self, rec) -> str:
        if not rec.created and not getattr(self, "_colmap", None):
            conn = self._connect()
            try:
                self._table_meta(conn.cursor(), rec.target)
            except Exception:  # noqa: BLE001
                pass
            finally:
                conn.close()
        return super()._undo_load(rec)


def _sf_norm(v: Any) -> Any:
    """Valeur Python de base (numpy, pandas, NaN / NaT → None)."""
    if v is None:
        return None
    item = getattr(v, "item", None)                 # scalaires numpy
    if item is not None and not isinstance(v, (str, bytes, bytearray, decimal.Decimal)):
        try:
            v = item()
        except (TypeError, ValueError):
            pass
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, decimal.Decimal) and v.is_nan():
        return None
    if hasattr(v, "to_pydatetime"):                 # pandas.Timestamp
        try:
            import pandas as pd
            if v is pd.NaT:
                return None
        except Exception:  # noqa: BLE001
            pass
        return v.to_pydatetime()
    if not isinstance(v, (str, bytes, bytearray, list, dict, tuple)):
        try:
            import pandas as pd
            if pd.isna(v):
                return None
        except Exception:  # noqa: BLE001
            pass
    if isinstance(v, tuple):
        return list(v)
    return v


def _sf_text(v: Any, code: Optional[int]) -> Optional[str]:
    """Valeur envoyée en texte ; Snowflake la convertit dans le type de la colonne."""
    v = _sf_norm(v)
    if v is None:
        return None
    if code in _JSON_CODES:
        if isinstance(v, str):
            return v                                 # déjà du JSON (source lue avec json: text)
        return json.dumps(v, ensure_ascii=False, default=str)
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, decimal.Decimal):
        return format(v, "f")
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, _dt.datetime):
        return v.isoformat(sep=" ")
    if isinstance(v, (_dt.date, _dt.time)):
        return v.isoformat()
    if isinstance(v, (bytes, bytearray)):
        return bytes(v).hex()
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False, default=str)
    return str(v)
