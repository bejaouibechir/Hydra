"""
Connecteur MySQL CDC — source : les changements d'une table (INSERT, UPDATE,
DELETE) lus dans le binlog, dans l'ordre des transactions.

    pip install "hydra-etl[mysql-cdc]"

    sources:
      orders_changes:
        type: mysql_cdc
        connection:
          host: ${MYSQL_HOST}
          port: 3306
          user: ${MYSQL_USER}         # droits REPLICATION SLAVE, REPLICATION CLIENT et SELECT
          password: ${MYSQL_PASSWORD}
          database: shop
          state: orders_mirror        # nom de la position enregistrée (défaut : <job>.<source>)
          server_id: 4201             # identifiant de réplique, unique sur le serveur (défaut : déduit de state)
          snapshot: true              # 1er run : la table entière, puis les changements (défaut : true)
          lag_warning_mb: 1024        # avertit au-delà de ce volume de binlog à relire (0 : jamais)
        extract:
          table: orders

Mêmes colonnes de suivi que la source PostgreSQL CDC, donc mêmes destinations
(upsert : delete appliqué, colonnes de suivi non écrites) :
- `_op` : insert, update, delete ou snapshot ;
- `_lsn` : position du changement dans le binlog (« binlog.000003:1234 ») ;
- `_commit_time` : heure du commit (datetime UTC ; None pour snapshot).

Position : MySQL n'a pas de slot. La position (fichier binlog + offset) est
enregistrée par Hydra dans `.hydra/cdc/<state>.json` à la racine du projet (ou
dans le dossier du job hors projet), et n'avance qu'après la publication réussie
de la destination : une panne fait relire les mêmes changements, que l'upsert
applique sans doublon.

Premier run : la position courante est lue, puis la table est lue dans un
instantané cohérent ; les changements faits entre les deux sont relus ensuite et,
appliqués en upsert, aboutissent au même état final. Aucun verrou global.

Surveillance : avant chaque lecture, le connecteur compare la position enregistrée
aux binlogs encore présents (SHOW BINARY LOGS).
- binlog à relire au-delà de `lag_warning_mb` : avertissement, le run continue ;
- fichier de la position purgé par MySQL (binlog_expire_logs_seconds) : le run
  échoue avec la marche à suivre ; il ne reprend jamais avec un trou.

Prérequis côté serveur : log_bin activé, binlog_format = ROW, binlog_row_image =
FULL (sinon un UPDATE ou un DELETE ne porte pas toute la ligne), MySQL 5.7 ou plus.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import re
import zlib
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

from hydra_etl.internal.connector.interface import Batch, Connector

logger = logging.getLogger(__name__)

CDC_COLUMNS = ("_op", "_lsn", "_commit_time")
_NAME_RE = re.compile(r"^[A-Za-z0-9_$]+$")
_STATE_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,100}$")


class MySQLCDCConnector(Connector):
    """Source MySQL CDC (binlog en format ROW, pilote mysql-replication)."""

    def __init__(self, name: str, config: Dict[str, Any]) -> None:
        super().__init__(name=name, config=config)
        conn = config.get("connection")
        if not isinstance(conn, dict):
            raise ValueError(f"MySQLCDCConnector [{self.name}]: 'connection' must be a mapping")
        self._conn_cfg = dict(conn)
        for k in ("user", "database"):
            if not self._conn_cfg.get(k):
                raise ValueError(f"MySQLCDCConnector [{self.name}]: connection.{k} is required")
        job_dir = Path(config.get("job_dir") or ".").resolve()
        state = str(self._conn_cfg.get("state") or f"{job_dir.name}.{self.name}").strip()
        if not _STATE_RE.match(state):
            raise ValueError(f"MySQLCDCConnector [{self.name}]: connection.state must be letters, digits, "
                             f"'_', '-' or '.' (got '{state}')")
        self.state = state
        sid = self._conn_cfg.get("server_id")
        try:
            self.server_id = int(sid) if sid not in (None, "") else 1_000_000 + zlib.crc32(state.encode()) % 1_000_000
        except (TypeError, ValueError):
            raise ValueError(f"MySQLCDCConnector [{self.name}]: connection.server_id must be an integer") from None
        if not 1 <= self.server_id <= 4294967295:
            raise ValueError(f"MySQLCDCConnector [{self.name}]: connection.server_id must be between 1 and 4294967295")
        self.snapshot = _flag(self._conn_cfg.get("snapshot"), True)
        self.lag_warning_mb = _number(self._conn_cfg.get("lag_warning_mb"), 1024,
                                      f"MySQLCDCConnector [{self.name}]: connection.lag_warning_mb")
        try:
            from hydra_etl.workflow.project import project_root_for_paths
            root = project_root_for_paths(job_dir)
        except Exception:  # noqa: BLE001
            root = None
        base = (root / ".hydra" / "cdc") if root else (job_dir / ".hydra-cdc")
        self.state_path = base / f"{state}.json"
        self._pending: Optional[Dict[str, Any]] = None
        self.last_status: Optional[Dict[str, Any]] = None

    # ── Connexion ────────────────────────────────────────────────────────
    def _settings(self) -> Dict[str, Any]:
        c = self._conn_cfg
        return {"host": c.get("host", "127.0.0.1"), "port": int(c.get("port", 3306)),
                "user": c.get("user"), "passwd": c.get("password") or ""}

    def _connect(self):
        try:
            import pymysql  # type: ignore
        except ImportError as e:
            raise ValueError(f"MySQLCDCConnector [{self.name}]: driver missing. "
                             f"Install it with 'pip install \"hydra-etl[mysql-cdc]\"'.") from e
        s = self._settings()
        try:
            return pymysql.connect(host=s["host"], port=s["port"], user=s["user"], password=s["passwd"],
                                   database=self._conn_cfg.get("database"), charset="utf8mb4")
        except Exception as e:
            raise ValueError(f"MySQLCDCConnector [{self.name}]: database connection failed.\n"
                             f"  DSN : {self._build_connection_string()}\n"
                             f"  Error: {type(e).__name__}: {e}") from e

    def _build_connection_string(self) -> str:
        c = self._conn_cfg
        return f"mysql://{c.get('user')}:***@{c.get('host', '127.0.0.1')}:{c.get('port', 3306)}/{c.get('database')}"

    def test_connection(self) -> None:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchall()
        finally:
            conn.close()

    # ── Position enregistrée ─────────────────────────────────────────────
    def _read_state(self) -> Optional[Dict[str, Any]]:
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except Exception as e:  # noqa: BLE001
            raise ValueError(f"MySQLCDCConnector [{self.name}]: unreadable position file {self.state_path}: {e}") from e
        if not isinstance(data, dict) or not data.get("log_file") or not isinstance(data.get("log_pos"), int):
            raise ValueError(f"MySQLCDCConnector [{self.name}]: invalid position file {self.state_path}")
        return data

    def _write_state(self, log_file: str, log_pos: int) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"log_file": log_file, "log_pos": log_pos,
                                   "server_id": self.server_id,
                                   "confirmed_at": _dt.datetime.now(_dt.timezone.utc).isoformat()}, indent=2),
                       encoding="utf-8")
        os.replace(tmp, self.state_path)

    # ── Serveur ──────────────────────────────────────────────────────────
    def _check_server(self, cur) -> None:
        cur.execute("SELECT @@log_bin, @@binlog_format, @@binlog_row_image")
        log_bin, fmt, image = cur.fetchone()
        if str(log_bin) not in ("1", "ON"):
            raise ValueError(f"MySQLCDCConnector [{self.name}]: the binlog is off. Start MySQL with "
                             f"log_bin enabled (default since MySQL 8.0).")
        if str(fmt).upper() != "ROW":
            raise ValueError(f"MySQLCDCConnector [{self.name}]: binlog_format is '{fmt}', CDC needs 'ROW'. "
                             f"Run SET PERSIST binlog_format = 'ROW'; (MySQL 8.0) or set it in my.cnf.")
        if str(image).upper() != "FULL":
            raise ValueError(f"MySQLCDCConnector [{self.name}]: binlog_row_image is '{image}', CDC needs 'FULL' "
                             f"so that each change carries the whole row. Run SET PERSIST binlog_row_image = 'FULL';")

    @staticmethod
    def _current_position(cur) -> Tuple[str, int]:
        for sql in ("SHOW BINARY LOG STATUS", "SHOW MASTER STATUS"):
            try:
                cur.execute(sql)
                row = cur.fetchone()
                if row:
                    return str(row[0]), int(row[1])
            except Exception:  # noqa: BLE001 - selon la version de MySQL
                continue
        raise ValueError("cannot read the current binlog position (SHOW BINARY LOG STATUS)")

    def binlog_status(self, cur) -> Dict[str, Any]:
        """État de la position : status ok | lost | missing, lag_bytes (binlog à relire)."""
        state = self._read_state()
        if state is None:
            return {"status": "missing", "lag_bytes": None, "position": None}
        cur.execute("SHOW BINARY LOGS")
        logs = [(str(r[0]), int(r[1])) for r in cur.fetchall()]
        names = [n for n, _ in logs]
        pos = f"{state['log_file']}:{state['log_pos']}"
        if state["log_file"] not in names:
            return {"status": "lost", "lag_bytes": None, "position": pos,
                    "oldest": names[0] if names else None}
        i = names.index(state["log_file"])
        lag = max(0, logs[i][1] - state["log_pos"]) + sum(s for _, s in logs[i + 1:])
        return {"status": "ok", "lag_bytes": lag, "position": pos}

    def cdc_status(self) -> Dict[str, Any]:
        """Forme commune aux sources CDC (conditions cdc.lag / cdc.status)."""
        conn = self._connect()
        try:
            st = self.binlog_status(conn.cursor())
        finally:
            conn.close()
        return {"status": st["status"], "lag_bytes": st["lag_bytes"],
                "detail": f"position {st['position']}" if st.get("position") else "no position yet"}

    def _check_position(self, cur) -> Optional[Dict[str, Any]]:
        st = self.binlog_status(cur)
        self.last_status = st
        if st["status"] == "lost":
            raise ValueError(
                f"MySQLCDCConnector [{self.name}]: the binlog of the saved position {st['position']} was "
                f"purged by MySQL (oldest binlog: {st.get('oldest')}); the changes made since the last "
                f"success can no longer be read. To rebuild the mirror: delete {self.state_path}, empty "
                f"the destination, run again (the first run copies the whole table). Keep binlogs longer "
                f"with binlog_expire_logs_seconds.")
        if st["status"] == "ok" and self.lag_warning_mb > 0 and st["lag_bytes"] > self.lag_warning_mb * 1024 * 1024:
            logger.warning("CDC source '%s': %s of binlog to read since the last success (above "
                           "lag_warning_mb = %s); a load that keeps failing lets MySQL purge them",
                           self.name, _mb(st["lag_bytes"]), self.lag_warning_mb)
        return st

    # ── Lecture ──────────────────────────────────────────────────────────
    def extract_batches(self, *, query: Optional[str] = None, table: Optional[str] = None,
                        batch_size: int = 10_000,
                        incremental: Optional[Dict[str, Any]] = None) -> Iterator[Batch]:
        if query:
            raise ValueError(f"MySQLCDCConnector [{self.name}]: a CDC source reads a table "
                             f"(extract.table), not a query")
        if not table:
            raise ValueError(f"MySQLCDCConnector [{self.name}]: extract.table is required")
        database, name = self._split_table(table)
        self._pending = None
        conn = self._connect()
        try:
            cur = conn.cursor()
            self._check_server(cur)
            cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = %s "
                        "AND table_name = %s", (database, name))
            if not cur.fetchone()[0]:
                raise ValueError(f"MySQLCDCConnector [{self.name}]: table {database}.{name} not found")
            state = self._check_position(cur)
            if state["status"] == "missing":
                log_file, log_pos = self._current_position(cur)
                self._pending = {"log_file": log_file, "log_pos": log_pos}
                if self.snapshot:
                    yield from self._snapshot(conn, database, name, batch_size)
            else:
                saved = self._read_state()
                log_file, log_pos = saved["log_file"], saved["log_pos"]
        finally:
            conn.close()
        yield from self._changes(database, name, log_file, log_pos, batch_size)

    def _split_table(self, table: str) -> Tuple[str, str]:
        parts = table.strip().split(".")
        if len(parts) == 1:
            parts = [str(self._conn_cfg["database"]), parts[0]]
        if len(parts) != 2 or not all(_NAME_RE.match(p) for p in parts):
            raise ValueError(f"MySQLCDCConnector [{self.name}]: invalid table name '{table}' "
                             f"(expected table or database.table)")
        return parts[0], parts[1]

    def _snapshot(self, conn, database: str, table: str, batch_size: int) -> Iterator[Batch]:
        """Premier run : la table entière (lignes _op = snapshot), dans un instantané cohérent."""
        import pymysql.cursors  # type: ignore
        cur = conn.cursor(pymysql.cursors.SSDictCursor)
        try:
            cur.execute("SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            cur.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT")
            cur.execute(f"SELECT * FROM `{database}`.`{table}`")
            while True:
                rows = cur.fetchmany(batch_size)
                if not rows:
                    break
                yield [{**dict(r), "_op": "snapshot", "_lsn": None, "_commit_time": None} for r in rows]
        finally:
            try:
                cur.close()
                conn.rollback()
            except Exception:  # noqa: BLE001
                pass

    def _changes(self, database: str, table: str, log_file: str, log_pos: int,
                 batch_size: int) -> Iterator[Batch]:
        try:
            from pymysqlreplication import BinLogStreamReader  # type: ignore
            from pymysqlreplication.event import QueryEvent, XidEvent  # type: ignore
            from pymysqlreplication.row_event import (  # type: ignore
                DeleteRowsEvent, UpdateRowsEvent, WriteRowsEvent)
        except ImportError as e:
            raise ValueError(f"MySQLCDCConnector [{self.name}]: driver missing. "
                             f"Install it with 'pip install \"hydra-etl[mysql-cdc]\"'.") from e
        stream = BinLogStreamReader(
            connection_settings=self._settings(), server_id=self.server_id,
            only_events=[WriteRowsEvent, UpdateRowsEvent, DeleteRowsEvent, XidEvent, QueryEvent],
            only_schemas=None, log_file=log_file, log_pos=log_pos, resume_stream=True, blocking=False)
        txn: Batch = []
        buf: Batch = []
        last: Optional[Tuple[str, int]] = None
        try:
            for ev in stream:
                if isinstance(ev, (XidEvent, QueryEvent)):
                    if isinstance(ev, QueryEvent) and str(getattr(ev, "query", "")).strip().upper() != "COMMIT":
                        continue
                    when = _dt.datetime.fromtimestamp(ev.timestamp, tz=_dt.timezone.utc)
                    for r in txn:
                        r["_commit_time"] = when
                    buf.extend(txn)                     # une transaction n'est émise qu'entière
                    txn = []
                    last = (stream.log_file, ev.packet.log_pos)
                    if len(buf) >= batch_size:
                        yield buf
                        buf = []
                    continue
                if ev.schema != database or ev.table != table:
                    continue
                lsn = f"{stream.log_file}:{ev.packet.log_pos}"
                for row in ev.rows:
                    if isinstance(ev, WriteRowsEvent):
                        values, op = row["values"], "insert"
                    elif isinstance(ev, UpdateRowsEvent):
                        values, op = row["after_values"], "update"
                    else:
                        values, op = row["values"], "delete"
                    txn.append({**{k: _value(v) for k, v in values.items()},
                                "_op": op, "_lsn": lsn, "_commit_time": None})
            if buf:
                yield buf
        finally:
            stream.close()
        if last is not None:
            self._pending = {"log_file": last[0], "log_pos": last[1]}

    # ── Confirmation après chargement réussi ─────────────────────────────
    def confirm_extract(self) -> Optional[str]:
        """Enregistre la position du dernier commit lu. Appelé par le job après la
        publication réussie de la destination. Renvoie la position (ou None)."""
        p = self._pending
        if not p:
            return None
        self._write_state(p["log_file"], p["log_pos"])
        self._pending = None
        pos = f"{p['log_file']}:{p['log_pos']}"
        logger.info("CDC source '%s': position %s saved in %s", self.name, pos, self.state_path)
        return pos

    # ── Écriture : refusée ───────────────────────────────────────────────
    def load_batches(self, batches: Iterable[Batch], *, table: str, mode: str = "append",
                     key: Optional[List[str]] = None, **_: Any) -> None:
        raise ValueError(f"MySQLCDCConnector [{self.name}]: a CDC source cannot be a destination; "
                         f"use type: mysql")

    def begin_load(self, **_: Any):
        raise ValueError(f"MySQLCDCConnector [{self.name}]: a CDC source cannot be a destination; "
                         f"use type: mysql")


def _value(v: Any) -> Any:
    """Valeur du binlog → valeur Python (texte décodé, JSON en dict / list)."""
    if isinstance(v, bytes):
        try:
            return v.decode("utf-8")
        except UnicodeDecodeError:
            return v
    return v


def _number(v: Any, default: float, label: str) -> float:
    if v is None or v == "":
        return default
    try:
        n = float(v)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a number (got {v!r})") from None
    if n < 0:
        raise ValueError(f"{label} must be >= 0 (got {v!r})")
    return n


def _mb(n: Optional[int]) -> str:
    return "?" if n is None else f"{n / (1024 * 1024):,.1f} MB"


def _flag(v: Any, default: bool) -> bool:
    if v is None or v == "":
        return default
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "yes", "on")
