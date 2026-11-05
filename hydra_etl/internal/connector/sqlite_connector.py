"""
Connecteur SQLite — source et destination, sans aucune dépendance.

`sqlite3` fait partie de Python : rien à installer, aucun serveur. Utile pour
les démos, les labs, les tests et les petites bases applicatives.

    sources:
      app:
        type: sqlite
        connection:
          path: ../../data/app.db        # relatif au dossier du job
        extract:
          table: orders                  # ou query: "SELECT ..."

    destinations:
      warehouse:
        type: sqlite
        connection:
          path: ../../outputs/warehouse.db
        load:
          table: orders
          mode: upsert                   # append | replace | upsert
          key: [order_id]

Chargement :
- la base et la table sont créées au premier lot si elles n'existent pas
  (types déduits du lot ; en upsert, la clé devient la clé primaire) ;
- tout ou rien par défaut dans les trois modes : une seule transaction pour
  le job, création de table comprise (SQLite sait annuler un CREATE TABLE) ;
- upsert : INSERT ... ON CONFLICT(clé) DO UPDATE (clé primaire ou index
  unique exigé sur ces colonnes) ;
- rollback d'un workflow (undo) : comme les autres bases.

La base passe en journal WAL : un job peut lire une table pendant qu'il en
écrit une autre dans le même fichier.
"""

from __future__ import annotations

import datetime as _dt
import decimal
import math
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from hydra_etl.internal.connector.base_db_connector import BaseDBConnector
from hydra_etl.internal.connector.interface import Batch
from hydra_etl.internal.connector.load_session import ATOMIC_MODES_ALL


class _Cursor:
    """Curseur sqlite3 qui accepte les marqueurs %s du code commun (undo)."""

    def __init__(self, cur: sqlite3.Cursor) -> None:
        self._c = cur

    @staticmethod
    def _sql(sql: str) -> str:
        return sql.replace("%s", "?")

    def execute(self, sql: str, params: Any = ()) -> "_Cursor":
        self._c.execute(self._sql(sql), tuple(params) if params is not None else ())
        return self

    def executemany(self, sql: str, seq: Any) -> "_Cursor":
        self._c.executemany(self._sql(sql), seq)
        return self

    def __getattr__(self, item: str) -> Any:
        return getattr(self._c, item)


class _Connection:
    """Connexion en transaction explicite : BEGIN à l'ouverture et après chaque
    commit / rollback. Le module sqlite3 (Python < 3.12) valide sinon les
    CREATE TABLE tout seuls, ce qui casserait le tout ou rien."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._conn.execute("BEGIN")

    def cursor(self) -> _Cursor:
        return _Cursor(self._conn.cursor())

    def commit(self) -> None:
        self._conn.execute("COMMIT")
        self._conn.execute("BEGIN")

    def rollback(self) -> None:
        if self._conn.in_transaction:
            self._conn.execute("ROLLBACK")
        self._conn.execute("BEGIN")

    def close(self) -> None:
        try:
            if self._conn.in_transaction:
                self._conn.execute("ROLLBACK")
        finally:
            self._conn.close()


def _py(v: Any) -> Any:
    """Valeur liable par sqlite3 (numpy, pandas, NaN, dates...)."""
    if v is None:
        return None
    item = getattr(v, "item", None)                # scalaires numpy
    if item is not None and not isinstance(v, (str, bytes)):
        try:
            v = item()
        except (TypeError, ValueError):
            pass
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float, str, bytes)):
        return v
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, (_dt.datetime, _dt.date, _dt.time)):
        return v.isoformat()
    try:
        import pandas as pd
        if v is pd.NaT or (not isinstance(v, (list, dict, tuple)) and pd.isna(v)):
            return None
        if isinstance(v, pd.Timestamp):
            return v.isoformat()
    except Exception:  # noqa: BLE001 - pandas absent ou valeur non scalaire
        pass
    if isinstance(v, (list, dict, tuple)):
        import json
        return json.dumps(v, ensure_ascii=False, default=str)
    return str(v)


def _sql_type(values: List[Any]) -> str:
    kinds = {type(v) for v in values if v is not None}
    if not kinds:
        return "TEXT"
    if kinds <= {int}:
        return "INTEGER"
    if kinds <= {int, float}:
        return "REAL"
    if kinds <= {bytes}:
        return "BLOB"
    return "TEXT"


class SQLiteConnector(BaseDBConnector):
    """Connecteur SQLite (module sqlite3 de Python)."""

    _wrap_load_value_errors = False

    # Une transaction SQLite ne coûte rien de plus : tout ou rien par défaut
    # dans les trois modes (`load.atomic: false` pour valider lot par lot).
    atomic_default_modes = ATOMIC_MODES_ALL

    def __init__(self, name: str, config: Dict[str, Any]) -> None:
        cfg = dict(config)
        conn = dict(cfg.get("connection") or {})
        cfg["connection"] = conn
        super().__init__(name, cfg)
        raw = conn.get("path") or conn.get("database")
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError(
                f"SQLiteConnector [{self.name}]: connection.path is required "
                f"(the database file, relative to the job folder)")
        path = Path(raw.strip()).expanduser()
        if not path.is_absolute():
            path = Path(cfg.get("job_dir") or ".") / path
        self.path = path.resolve()

    # ── Connexion ────────────────────────────────────────────────────────
    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        raw = sqlite3.connect(str(self.path), timeout=30, isolation_level=None)
        try:
            raw.execute("PRAGMA journal_mode=WAL")
        except sqlite3.DatabaseError:
            pass                                     # système de fichiers sans WAL
        return _Connection(raw)

    def _connect_read(self) -> sqlite3.Connection:
        if not self.path.is_file():
            raise ValueError(f"SQLiteConnector [{self.name}]: database file not found: {self.path}")
        return sqlite3.connect(f"{self.path.as_uri()}?mode=ro", uri=True, timeout=30)

    def _build_connection_string(self) -> str:
        return f"sqlite:///{self.path}"

    def _build_columns_query(self, table: str) -> str:
        return f"SELECT * FROM {self._q(table)} LIMIT 0"

    def test_connection(self) -> None:
        """Base existante : ouverte en lecture seule. Absente : seul le dossier est
        vérifié (une destination la crée au premier lot ; rien n'est créé ici)."""
        if not self.path.exists():
            parent = self.path.parent
            while not parent.exists() and parent != parent.parent:
                parent = parent.parent
            if not parent.is_dir():
                raise ValueError(f"SQLiteConnector [{self.name}]: no folder for {self.path}")
            return
        try:
            conn = self._connect_read()
            conn.execute("SELECT 1").fetchone()
            conn.close()
        except Exception as e:
            raise ValueError(
                f"SQLiteConnector [{self.name}]: connection test failed.\n"
                f"  Database: {self.path}\n  Error: {type(e).__name__}: {e}") from e

    # ── Extract ──────────────────────────────────────────────────────────
    def extract_batches(self, *, query: Optional[str] = None, table: Optional[str] = None,
                        batch_size: int = 10_000,
                        incremental: Optional[Dict[str, Any]] = None) -> Iterator[Batch]:
        if incremental:
            raise ValueError(f"SQLiteConnector [{self.name}]: incremental extraction is not supported yet")
        if query and table:
            raise ValueError(f"SQLiteConnector [{self.name}]: 'query' and 'table' are mutually exclusive")
        if not query and not table:
            raise ValueError(f"SQLiteConnector [{self.name}]: 'query' or 'table' is required")
        sql = query.strip() if query else f"SELECT * FROM {self._q(table.strip())}"
        conn = self._connect_read()
        try:
            yield from self._execute_query_batches(conn=conn, query=sql, batch_size=batch_size)
        finally:
            conn.close()

    # ── Load (session par job : base_db_connector.DBLoadSession) ─────────
    def _check_load_args(self, table: str, mode: str, key: Optional[List[str]]):
        if not isinstance(table, str) or not table.strip():
            raise ValueError(f"SQLiteConnector [{self.name}]: 'table' must be a non-empty name")
        if mode not in ("append", "replace", "upsert"):
            raise ValueError(f"SQLiteConnector [{self.name}]: mode '{mode}' is not supported. "
                             f"Supported: append, replace, upsert")
        if isinstance(key, str):
            key = [key]
        if mode == "upsert":
            if not key or not all(isinstance(k, str) and k.strip() for k in key):
                raise ValueError(f"SQLiteConnector [{self.name}]: mode 'upsert' needs load.key "
                                 f"(the columns that identify a row)")
            key = [k.strip() for k in key]
        return table.strip(), key

    def _load_prepare(self, cur, *, table, mode, key, atomic, commit, **_):
        exists = self._table_exists(cur, table)
        if mode == "replace" and exists:
            cur.execute(f"DELETE FROM {self._q(table)}")
        if mode == "upsert" and exists:
            self._check_upsert_key(cur, table, key)
        return {"table": table, "mode": mode, "key": key, "columns": None, "exists": exists}

    def _load_write(self, cur, ctx, batch, *, commit):
        rows = list(batch)
        if not rows:
            return
        if ctx["columns"] is None:
            first = rows[0]
            if not isinstance(first, dict) or not first:
                raise ValueError(f"SQLiteConnector [{self.name}]: invalid batch (first row empty)")
            ctx["columns"] = [c for c in first.keys() if isinstance(c, str) and c.strip()]
            if not ctx["exists"]:
                self._create_table(cur, ctx, rows)
                ctx["exists"] = True
        cols = ctx["columns"]
        values = [tuple(_py(r.get(c)) for c in cols) for r in rows]
        col_sql = ", ".join(self._q(c) for c in cols)
        sql = f"INSERT INTO {self._q(ctx['table'])} ({col_sql}) VALUES ({', '.join(['?'] * len(cols))})"
        if ctx["mode"] == "upsert":
            key = ctx["key"]
            missing = [k for k in key if k not in cols]
            if missing:
                raise ValueError(f"SQLiteConnector [{self.name}]: upsert key {missing} is not in the data "
                                 f"(columns: {cols})")
            upd = [c for c in cols if c not in key]
            conflict = ", ".join(self._q(k) for k in key)
            sql += (f" ON CONFLICT({conflict}) DO UPDATE SET "
                    + ", ".join(f"{self._q(c)} = excluded.{self._q(c)}" for c in upd)
                    if upd else f" ON CONFLICT({conflict}) DO NOTHING")
        cur.executemany(sql, values)

    def _create_table(self, cur, ctx, rows) -> None:
        cols = ctx["columns"]
        sample = rows[:1000]
        defs = [f"{self._q(c)} {_sql_type([_py(r.get(c)) for r in sample])}" for c in cols]
        if ctx["mode"] == "upsert":
            defs.append(f"PRIMARY KEY ({', '.join(self._q(k) for k in ctx['key'])})")
        cur.execute(f"CREATE TABLE {self._q(ctx['table'])} ({', '.join(defs)})")

    def _check_upsert_key(self, cur, table: str, key: List[str]) -> None:
        """L'upsert exige une clé primaire ou un index unique sur exactement ces colonnes."""
        want = sorted(key)
        cur.execute(f"PRAGMA table_info({self._q(table)})")
        pk = sorted(r[1] for r in cur.fetchall() if r[5])
        if pk == want:
            return
        cur.execute(f"PRAGMA index_list({self._q(table)})")
        for idx in cur.fetchall():
            if idx[2]:                                  # unique
                cur.execute(f"PRAGMA index_info({self._q(idx[1])})")
                if sorted(r[2] for r in cur.fetchall()) == want:
                    return
        raise ValueError(
            f"SQLiteConnector [{self.name}]: upsert into '{table}' needs a PRIMARY KEY or a UNIQUE "
            f"index on {key}. Create it: CREATE UNIQUE INDEX ux_{table}_{'_'.join(key)} "
            f"ON {table} ({', '.join(key)});")

    # ── Annulation (rollback d'un workflow, voir undo.py) ────────────────
    def _q_table(self, table: str) -> str:
        return self._q(table)

    def _q_col(self, column: str) -> str:
        return self._q(column)

    def _table_exists(self, cur, table: str) -> bool:
        cur.execute("SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = ?", (table,))
        row = cur.fetchone()
        return bool(row and row[0])

    def _q(self, identifier: str) -> str:
        ident = (identifier or "").strip()
        if not ident:
            raise ValueError(f"SQLiteConnector [{self.name}]: empty SQL identifier")
        for bad in ('"', ";", "--", "/*", "*/"):
            if bad in ident:
                raise ValueError(f"SQLiteConnector [{self.name}]: invalid SQL identifier: {identifier!r}")
        return f'"{ident}"'
