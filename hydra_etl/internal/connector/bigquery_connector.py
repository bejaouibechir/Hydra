"""
Connecteur BigQuery — source et destination.

    pip install "hydra-etl[bigquery]"

    sources:
      bq:
        type: bigquery
        connection:
          project: my-project                       # obligatoire
          dataset: sales                            # dataset par défaut (facultatif)
          location: EU                              # facultatif
          credentials_file: ../../keys/sa.json      # compte de service ; sinon identifiants
                                                    # par défaut (gcloud auth application-default login)
        extract:
          table: orders                             # orders, sales.orders ou project.sales.orders
                                                    # ou query: "SELECT ..."

    destinations:
      bq:
        type: bigquery
        connection: { project: my-project, dataset: sales }
        load:
          table: orders
          mode: upsert                              # append | replace | upsert
          key: [order_id]

Lecture : les types de BigQuery arrivent exacts (INT64 → int, NUMERIC / BIGNUMERIC →
Decimal, DATETIME → datetime sans fuseau, TIMESTAMP → datetime avec fuseau, JSON →
dict / list, ou texte avec json: text). `extract.query` doit être un SELECT (ou WITH).

Écriture — tout ou rien dans les trois modes, sans coût de chargement :
- chaque lot est chargé (job de chargement, gratuit) dans une table de transit du même
  dataset, `_hydra_stage_…`, toutes colonnes en texte, expirée après 24 h ;
- à la publication, UNE instruction (ou une transaction) écrit dans la table cible en
  convertissant chaque valeur dans le type de sa colonne (CAST, PARSE_JSON, FROM_BASE64) :
  aucun entier ni décimal ne passe par un float ;
  append = INSERT … SELECT ; replace = DELETE + INSERT dans une transaction ;
  upsert = MERGE (dernière ligne d'une clé gagnante ; suppressions d'une source CDC) ;
  table absente = CREATE TABLE … AS SELECT, types déduits des données ;
- `load.atomic: false` publie après chaque lot ;
- noms de colonnes rapprochés de ceux de la table sans tenir compte de la casse (règle de
  BigQuery) ; une colonne absente de la table, ou de type RECORD / ARRAY, est refusée.
- Annulation par le rollback d'un workflow : pas encore disponible.
"""

from __future__ import annotations

import base64
import datetime as _dt
import decimal
import json
import logging
import math
import re
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

from hydra_etl.internal.connector.interface import Batch, Connector
from hydra_etl.internal.connector.load_session import ATOMIC_MODES_ALL, LoadSession

logger = logging.getLogger(__name__)

_READ_ONLY_RE = re.compile(r"^\s*(\(|with\b|select\b)", re.IGNORECASE)
_PROJECT_RE = re.compile(r"^[a-z][a-z0-9\-]{4,61}[a-z0-9]$|^[A-Za-z0-9_\-.:]+$")
_NAME_RE = re.compile(r"^[A-Za-z0-9_\-]+$")
_CDC_COLUMNS = ("_op", "_lsn", "_commit_time")

# Type BigQuery → expression qui convertit le texte de la table de transit.
_CASTS = {
    "INT64": "CAST({c} AS INT64)", "INTEGER": "CAST({c} AS INT64)",
    "NUMERIC": "CAST({c} AS NUMERIC)", "DECIMAL": "CAST({c} AS NUMERIC)",
    "BIGNUMERIC": "CAST({c} AS BIGNUMERIC)", "BIGDECIMAL": "CAST({c} AS BIGNUMERIC)",
    "FLOAT64": "CAST({c} AS FLOAT64)", "FLOAT": "CAST({c} AS FLOAT64)",
    "BOOL": "CAST({c} AS BOOL)", "BOOLEAN": "CAST({c} AS BOOL)",
    "DATE": "CAST({c} AS DATE)", "DATETIME": "CAST({c} AS DATETIME)",
    "TIME": "CAST({c} AS TIME)", "TIMESTAMP": "CAST({c} AS TIMESTAMP)",
    "JSON": "PARSE_JSON({c})", "BYTES": "FROM_BASE64({c})",
    "GEOGRAPHY": "ST_GEOGFROMTEXT({c})", "STRING": "{c}",
}


class BigQueryConnector(Connector):
    """Source et destination BigQuery (pilote google-cloud-bigquery)."""

    atomic_load_modes = ATOMIC_MODES_ALL
    atomic_default_modes = ATOMIC_MODES_ALL
    undo_load_modes = frozenset()

    def __init__(self, name: str, config: Dict[str, Any]) -> None:
        super().__init__(name=name, config=config)
        conn = config.get("connection")
        if not isinstance(conn, dict):
            raise ValueError(f"BigQueryConnector [{self.name}]: 'connection' must be a mapping")
        self._conn_cfg = dict(conn)
        project = str(self._conn_cfg.get("project") or "").strip()
        if not project:
            raise ValueError(f"BigQueryConnector [{self.name}]: connection.project is required "
                             f"(the Google Cloud project id)")
        if not _PROJECT_RE.match(project):
            raise ValueError(f"BigQueryConnector [{self.name}]: invalid project id '{project}'")
        self.project = project
        ds = str(self._conn_cfg.get("dataset") or "").strip() or None
        if ds is not None and not _NAME_RE.match(ds):
            raise ValueError(f"BigQueryConnector [{self.name}]: invalid dataset name '{ds}'")
        self.dataset = ds
        self.location = self._conn_cfg.get("location") or None
        js = str(self._conn_cfg.get("json") or "parse").strip().lower()
        if js not in ("parse", "text"):
            raise ValueError(f"BigQueryConnector [{self.name}]: connection.json must be "
                             f"'parse' or 'text' (got '{js}')")
        self.json_mode = js
        cred = self._conn_cfg.get("credentials_file")
        self.credentials_file: Optional[Path] = None
        if cred:
            p = Path(str(cred)).expanduser()
            if not p.is_absolute():
                p = Path(config.get("job_dir") or ".") / p
            self.credentials_file = p.resolve()

    # ── Client ───────────────────────────────────────────────────────────
    def _make_client(self):
        try:
            from google.cloud import bigquery  # type: ignore
        except ImportError as e:
            raise ValueError(
                f"BigQueryConnector [{self.name}]: the BigQuery driver is not installed. "
                f"Install it with 'pip install \"hydra-etl[bigquery]\"'.") from e
        kwargs: Dict[str, Any] = {"project": self.project}
        if self.location:
            kwargs["location"] = self.location
        if self.credentials_file is not None:
            if not self.credentials_file.is_file():
                raise ValueError(f"BigQueryConnector [{self.name}]: credentials file not found: "
                                 f"{self.credentials_file}")
            from google.oauth2 import service_account  # type: ignore
            kwargs["credentials"] = service_account.Credentials.from_service_account_file(
                str(self.credentials_file))
        endpoint = self._conn_cfg.get("api_endpoint")
        if endpoint:                                 # émulateur
            from google.api_core.client_options import ClientOptions  # type: ignore
            kwargs["client_options"] = ClientOptions(api_endpoint=str(endpoint))
            if "credentials" not in kwargs:
                from google.auth.credentials import AnonymousCredentials  # type: ignore
                kwargs["credentials"] = AnonymousCredentials()
        return bigquery.Client(**kwargs)

    def _client(self):
        if getattr(self, "_cli", None) is None:
            self._cli = self._make_client()
        return self._cli

    def _error(self, what: str, e: Exception) -> ValueError:
        msg = getattr(e, "message", None) or str(e)
        return ValueError(f"BigQueryConnector [{self.name}]: {what}.\n  Error: {type(e).__name__}: {msg}")

    def _run(self, sql: str, what: str):
        try:
            return self._client().query(sql).result()
        except ValueError:
            raise
        except Exception as e:  # noqa: BLE001 - erreurs Google normalisées
            raise self._error(what, e) from e

    # ── Noms ─────────────────────────────────────────────────────────────
    def _ref(self, table: str) -> str:
        """project.dataset.table (sans accents graves)."""
        t = (table or "").strip().strip("`")
        parts = [p.strip("`") for p in t.split(".")] if t else []
        if len(parts) == 1 and self.dataset:
            parts = [self.project, self.dataset] + parts
        elif len(parts) == 2:
            parts = [self.project] + parts
        ok = (len(parts) == 3 and _PROJECT_RE.match(parts[0]) and _NAME_RE.match(parts[1])
              and _NAME_RE.match(parts[2]))
        if not ok:
            raise ValueError(
                f"BigQueryConnector [{self.name}]: invalid table name '{table}' (expected table with "
                f"connection.dataset, dataset.table or project.dataset.table)")
        return ".".join(parts)

    @staticmethod
    def _q(ref: str) -> str:
        return f"`{ref}`"

    @staticmethod
    def _qc(column: str) -> str:
        return "`" + column.replace("\\", "\\\\").replace("`", "\\`") + "`"

    def _build_connection_string(self) -> str:
        return f"bigquery://{self.project}" + (f"/{self.dataset}" if self.dataset else "")

    def test_connection(self) -> None:
        try:
            list(self._client().query("SELECT 1").result())
        except Exception as e:  # noqa: BLE001
            raise ValueError(
                f"BigQueryConnector [{self.name}]: connection test failed.\n"
                f"  DSN : {self._build_connection_string()}\n"
                f"  Error: {type(e).__name__}: {getattr(e, 'message', None) or e}") from e

    # ── Lecture ──────────────────────────────────────────────────────────
    def extract_batches(self, *, query: Optional[str] = None, table: Optional[str] = None,
                        batch_size: int = 10_000,
                        incremental: Optional[Dict[str, Any]] = None) -> Iterator[Batch]:
        if incremental:
            raise ValueError(f"BigQueryConnector [{self.name}]: incremental extraction is not supported yet")
        if not isinstance(batch_size, int) or batch_size < 1:
            raise ValueError(f"BigQueryConnector [{self.name}]: 'batch_size' must be an integer >= 1")
        if query and table:
            raise ValueError(f"BigQueryConnector [{self.name}]: 'query' and 'table' are mutually exclusive")
        if not query and not table:
            raise ValueError(f"BigQueryConnector [{self.name}]: 'query' or 'table' is required")
        if query:
            sql = query.strip().rstrip(";").strip()
            if not _READ_ONLY_RE.match(sql):
                raise ValueError(f"BigQueryConnector [{self.name}]: a source only reads; extract.query "
                                 f"must start with SELECT or WITH")
        else:
            sql = f"SELECT * FROM {self._q(self._ref(table))}"
        limit = (self.config.get("extract") or {}).get("limit")
        if limit:
            sql = f"SELECT * FROM ({sql}) LIMIT {int(limit)}"
        try:
            result = self._client().query(sql).result(page_size=batch_size)
        except Exception as e:  # noqa: BLE001
            raise self._error("query failed", e) from e
        json_cols = {f.name for f in (getattr(result, "schema", None) or [])
                     if str(f.field_type).upper() == "JSON"}
        buf: Batch = []
        for row in result:
            r = dict(row.items())
            for c in json_cols:
                v = r.get(c)
                if self.json_mode == "parse" and isinstance(v, str):
                    r[c] = json.loads(v)
                elif self.json_mode == "text" and v is not None and not isinstance(v, str):
                    r[c] = json.dumps(v, ensure_ascii=False)
            buf.append(r)
            if len(buf) >= batch_size:
                yield buf
                buf = []
        if buf:
            yield buf

    # ── Écriture ─────────────────────────────────────────────────────────
    def begin_load(self, *, table: str, mode: str = "append", key: Optional[List[str]] = None,
                   atomic: bool = True, undo: bool = False, **_: Any) -> "BigQueryLoadSession":
        if undo:
            from hydra_etl.internal.connector.undo import UndoUnavailable
            raise UndoUnavailable(f"BigQueryConnector [{self.name}]: undoing a BigQuery load (rollback: "
                                  f"true) is not available yet")
        if mode not in ("append", "replace", "upsert"):
            raise ValueError(f"BigQueryConnector [{self.name}]: mode '{mode}' is not supported. "
                             f"Supported: append, replace, upsert")
        if isinstance(key, str):
            key = [key]
        if mode == "upsert" and (not key or not all(isinstance(k, str) and k.strip() for k in key)):
            raise ValueError(f"BigQueryConnector [{self.name}]: mode 'upsert' needs load.key "
                             f"(the columns that identify a row)")
        ref = self._ref(table)
        return BigQueryLoadSession(self, ref=ref, table=table, mode=mode,
                                   key=[k.strip() for k in key] if key else None, atomic=atomic)

    def load_batches(self, batches: Iterable[Batch], *, table: str, mode: str = "append",
                     key: Optional[List[str]] = None, **_: Any) -> None:
        session = self.begin_load(table=table, mode=mode, key=key, atomic=True)
        try:
            for b in batches:
                session.stage(b)
            session.publish()
        except BaseException:
            session.abort()
            raise

    def _table_fields(self, ref: str) -> Optional[List[Tuple[str, str, str]]]:
        """[(nom, type, mode)] de la table, ou None si elle n'existe pas."""
        try:
            t = self._client().get_table(ref)
        except Exception as e:  # noqa: BLE001
            if type(e).__name__ == "NotFound":
                return None
            raise self._error(f"cannot read table {ref}", e) from e
        return [(f.name, str(f.field_type).upper(), str(getattr(f, "mode", None) or "NULLABLE").upper())
                for f in t.schema]

    def _new_type(self, column: str, values: List[Any]) -> str:
        vals = [v for v in values if v is not None]
        if not vals:
            return "STRING"
        if all(isinstance(v, bool) for v in vals):
            return "BOOL"
        if all(isinstance(v, int) and not isinstance(v, bool) for v in vals):
            if all(-2 ** 63 <= v < 2 ** 63 for v in vals):
                return "INT64"
        if all(isinstance(v, (int, decimal.Decimal)) and not isinstance(v, bool) for v in vals):
            scale = digits = 0
            for v in vals:
                t = decimal.Decimal(v).as_tuple()
                e = t.exponent if isinstance(t.exponent, int) else 0
                s = max(0, -e)
                scale = max(scale, s)
                digits = max(digits, len(t.digits) + max(0, e) - s)
            if scale <= 9 and digits <= 29:
                return "NUMERIC"
            if scale <= 38 and digits <= 38:
                return "BIGNUMERIC"
            raise ValueError(f"BigQueryConnector [{self.name}]: column '{column}' holds numbers too large "
                             f"for BIGNUMERIC ({digits} digits before the point, {scale} after). Cast it "
                             f"to str (cast step) to load it as text, or create the table yourself.")
        if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals):
            return "FLOAT64"
        if all(isinstance(v, _dt.datetime) for v in vals):
            return "TIMESTAMP" if all(v.tzinfo is not None for v in vals) else "DATETIME"
        if all(isinstance(v, _dt.date) and not isinstance(v, _dt.datetime) for v in vals):
            return "DATE"
        if all(isinstance(v, _dt.date) for v in vals):
            return "DATETIME"
        if all(isinstance(v, _dt.time) for v in vals):
            return "TIME"
        if all(isinstance(v, (dict, list)) for v in vals):
            return "JSON"
        if all(isinstance(v, (bytes, bytearray)) for v in vals):
            return "BYTES"
        return "STRING"


class BigQueryLoadSession(LoadSession):
    """Lots → table de transit (texte) ; publication en une instruction."""

    def __init__(self, c: BigQueryConnector, *, ref: str, table: str, mode: str,
                 key: Optional[List[str]], atomic: bool) -> None:
        super().__init__(target=f"BigQueryConnector:{ref}", table=table, mode=mode, atomic=atomic)
        self._c = c
        self.ref = ref
        self.key = key
        self.fields: Optional[List[Tuple[str, str, str]]] = None
        self.exists = False
        self.columns: Optional[List[str]] = None       # noms dans les données
        self.targets: List[Tuple[str, str]] = []       # (nom dans la table, type)
        self.stage_ref: Optional[str] = None
        self.seq = 0
        self.applied = False
        try:
            self.fields = c._table_fields(ref)
            self.exists = self.fields is not None
            if self.exists and mode == "upsert":
                self._resolve(key, what="upsert key")
        except BaseException:
            self._release()
            raise

    # ── Colonnes ──
    def _resolve(self, names: List[str], *, what: str) -> List[Tuple[str, str, str]]:
        exact = {f[0]: f for f in self.fields or []}
        upper = {f[0].upper(): f for f in self.fields or []}
        out, missing = [], []
        for n in names:
            f = exact.get(n) or upper.get(n.upper())
            (out.append(f) if f else missing.append(n))
        if missing:
            have = ", ".join(f[0] for f in self.fields or [])
            raise ValueError(f"BigQueryConnector [{self._c.name}]: {what} {missing} not found in table "
                             f"{self.ref} (columns: {have}). Add the column to the table, or rename or "
                             f"drop it before loading.")
        return out

    def _setup(self, rows: List[Dict[str, Any]]) -> None:
        names = [c for c in rows[0].keys() if isinstance(c, str) and c.strip() and c not in _CDC_COLUMNS]
        seen: Dict[str, str] = {}
        for n in names:
            if n.upper() in seen:
                raise ValueError(f"BigQueryConnector [{self._c.name}]: columns '{seen[n.upper()]}' and '{n}' "
                                 f"differ only by case; BigQuery would store them in the same column. "
                                 f"Rename one of them (rename step) before loading.")
            seen[n.upper()] = n
        if self.mode == "upsert":
            missing = [k for k in self.key if k not in names]
            if missing:
                raise ValueError(f"BigQueryConnector [{self._c.name}]: upsert key {missing} is not in the "
                                 f"data (columns: {names})")
        if self.exists:
            fields = self._resolve(names, what="column")
            bad = [f[0] for f in fields if f[2] == "REPEATED" or f[1] not in _CASTS]
            if bad:
                raise ValueError(f"BigQueryConnector [{self._c.name}]: columns {bad} of {self.ref} are "
                                 f"RECORD, ARRAY or another type Hydra ETL cannot write yet")
            self.targets = [(f[0], f[1]) for f in fields]
        else:
            self.targets = [(n, self._c._new_type(n, [_norm(r.get(n)) for r in rows])) for n in names]
        self.columns = names
        cli = self._c._client()
        from google.cloud import bigquery  # type: ignore
        dataset = self.ref.rsplit(".", 1)[0]
        base = re.sub(r"[^A-Za-z0-9_]", "_", self.ref.rsplit(".", 1)[1])[:40]
        self.stage_ref = f"{dataset}._hydra_stage_{base}_{uuid.uuid4().hex[:8]}"
        schema = ([bigquery.SchemaField("_hydra_seq", "INT64"), bigquery.SchemaField("_hydra_op", "STRING")]
                  + [bigquery.SchemaField(f"c{i}", "STRING") for i in range(len(names))])
        t = bigquery.Table(self.stage_ref, schema=schema)
        t.expires = _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(days=1)
        try:
            cli.create_table(t)
        except Exception as e:  # noqa: BLE001
            raise self._c._error(f"cannot create the staging table {self.stage_ref} (the user needs "
                                 f"CREATE TABLE on the dataset)", e) from e

    # ── Lots ──
    def _stage(self, batch: Any) -> None:
        rows = [r for r in batch]
        ops: Optional[List[str]] = None
        if rows and isinstance(rows[0], dict) and "_op" in rows[0]:
            rows, ops = self._cdc(rows)
        if not rows:
            return
        if self.columns is None:
            self._setup(rows)
        payload = []
        for i, r in enumerate(rows):
            if self.mode == "upsert" and any(_norm(r.get(k)) is None for k in self.key):
                raise ValueError(f"BigQueryConnector [{self._c.name}]: a row has no value for the upsert "
                                 f"key {self.key}: {dict((k, r.get(k)) for k in self.key)}")
            self.seq += 1
            item = {"_hydra_seq": self.seq, "_hydra_op": ops[i] if ops else "upsert"}
            for j, (c, (_, typ)) in enumerate(zip(self.columns, self.targets)):
                item[f"c{j}"] = _text(r.get(c), typ)
            payload.append(item)
        from google.cloud import bigquery  # type: ignore
        cfg = bigquery.LoadJobConfig(write_disposition="WRITE_APPEND",
                                     source_format="NEWLINE_DELIMITED_JSON")
        try:
            self._c._client().load_table_from_json(payload, self.stage_ref, job_config=cfg).result()
        except Exception as e:  # noqa: BLE001
            raise self._c._error(f"batch load into {self.stage_ref} failed", e) from e
        if not self.atomic:
            self._apply()
            self._c._run(f"DELETE FROM {self._c._q(self.stage_ref)} WHERE TRUE", "staging cleanup failed")

    def _cdc(self, rows):
        """Lot d'une source CDC : état final par clé ; suppressions marquées « delete »."""
        if self.mode != "upsert":
            raise ValueError(f"BigQueryConnector [{self._c.name}]: changes from a CDC source need "
                             f"mode: upsert with load.key")
        from hydra_etl.internal.connector.postgresql_connector import PostgreSQLConnector

        class _N:                                       # nom et colonnes attendus par _split_changes
            name = self._c.name
            _CDC_COLUMNS = _CDC_COLUMNS
        upserts, changes = PostgreSQLConnector._split_changes(_N(), rows, self.key)
        if changes["partial"]:
            raise ValueError(
                f"BigQueryConnector [{self._c.name}]: {len(changes['partial'])} change(s) do not carry every "
                f"column (large values left unchanged by PostgreSQL). Set REPLICA IDENTITY FULL on the "
                f"source table so that each change carries the whole row.")
        names = [c for c in rows[0].keys() if c not in _CDC_COLUMNS]
        deletes = [dict({c: None for c in names}, **dict(zip(self.key, k))) for k in changes["delete"]]
        return upserts + deletes, ["upsert"] * len(upserts) + ["delete"] * len(deletes)

    # ── Publication ──
    def _select(self, dedup: bool) -> str:
        exprs = [_CASTS[typ].format(c=f"c{j}") + f" AS {self._c._qc(name)}"
                 for j, (name, typ) in enumerate(self.targets)]
        sql = f"SELECT {', '.join(exprs)}, _hydra_op FROM {self._c._q(self.stage_ref)}"
        if dedup:
            idx = [self.columns.index(k) for k in self.key]
            part = ", ".join(f"c{i}" for i in idx)
            sql += f" WHERE TRUE QUALIFY ROW_NUMBER() OVER (PARTITION BY {part} ORDER BY _hydra_seq DESC) = 1"
        return sql

    def _apply(self) -> None:
        if self.stage_ref is None:
            return
        q, qc = self._c._q(self.ref), self._c._qc
        cols = ", ".join(qc(n) for n, _ in self.targets)
        upsert = self.mode == "upsert"
        if not self.exists:
            src = self._select(dedup=upsert)
            names = ", ".join(qc(n) for n, _ in self.targets)
            self._c._run(f"CREATE TABLE {q} AS SELECT {names} FROM ({src}) WHERE _hydra_op != 'delete'",
                         f"cannot create table {self.ref}")
            self.exists = True
            self.fields = self._c._table_fields(self.ref)
            logger.info("BigQuery destination '%s': table %s created (%s)", self._c.name, self.ref,
                        ", ".join(f"{n} {t}" for n, t in self.targets))
        elif upsert:
            keys = {f[0] for f in self._resolve(self.key, what="upsert key")}
            on = " AND ".join(f"T.{qc(k)} = S.{qc(k)}" for k in sorted(keys))
            upd = [n for n, _ in self.targets if n not in keys]
            sql = (f"MERGE {q} T USING ({self._select(dedup=True)}) S ON {on} "
                   f"WHEN MATCHED AND S._hydra_op = 'delete' THEN DELETE ")
            if upd:
                sql += "WHEN MATCHED THEN UPDATE SET " + ", ".join(f"{qc(n)} = S.{qc(n)}" for n in upd) + " "
            sql += (f"WHEN NOT MATCHED AND S._hydra_op != 'delete' THEN INSERT ({cols}) "
                    f"VALUES ({', '.join('S.' + qc(n) for n, _ in self.targets)})")
            self._c._run(sql, f"MERGE into {self.ref} failed")
        else:
            insert = f"INSERT INTO {q} ({cols}) SELECT {cols} FROM ({self._select(dedup=False)})"
            if self.mode == "replace" and not self.applied:
                self._c._run(f"BEGIN TRANSACTION; DELETE FROM {q} WHERE TRUE; {insert}; COMMIT TRANSACTION;",
                             f"replace of {self.ref} failed")
            else:
                self._c._run(insert, f"insert into {self.ref} failed")
        self.applied = True

    def _publish(self) -> None:
        try:
            if self.atomic:
                self._apply()
        finally:
            self._drop_stage()

    def _abort(self) -> None:
        self._drop_stage()

    def _drop_stage(self) -> None:
        if self.stage_ref:
            try:
                self._c._client().delete_table(self.stage_ref, not_found_ok=True)
            except Exception as e:  # noqa: BLE001
                logger.warning("BigQuery: staging table %s not dropped (%s); it expires within 24 h",
                               self.stage_ref, e)
            self.stage_ref = None


def _norm(v: Any) -> Any:
    """Valeur Python de base (numpy, pandas, NaN / NaT → None)."""
    if v is None:
        return None
    item = getattr(v, "item", None)
    if item is not None and not isinstance(v, (str, bytes, bytearray, decimal.Decimal)):
        try:
            v = item()
        except (TypeError, ValueError):
            pass
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, decimal.Decimal) and v.is_nan():
        return None
    if hasattr(v, "to_pydatetime"):
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


def _text(v: Any, typ: str) -> Optional[str]:
    """Texte que BigQuery convertit dans le type de la colonne."""
    v = _norm(v)
    if v is None:
        return None
    if typ == "JSON":
        return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)
    if typ == "BYTES":
        b = bytes(v) if isinstance(v, (bytes, bytearray)) else str(v).encode("utf-8")
        return base64.b64encode(b).decode("ascii")
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, decimal.Decimal):
        return format(v, "f")
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, _dt.datetime):
        if typ == "DATETIME" and v.tzinfo is not None:
            v = v.replace(tzinfo=None)              # heure murale, comme une colonne sans fuseau
        return v.isoformat(sep=" ")
    if isinstance(v, (_dt.date, _dt.time)):
        return v.isoformat()
    if isinstance(v, (bytes, bytearray)):
        return base64.b64encode(bytes(v)).decode("ascii")
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False, default=str)
    return str(v)
