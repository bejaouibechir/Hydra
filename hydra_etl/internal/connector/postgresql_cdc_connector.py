"""
Connecteur PostgreSQL CDC — source : les changements d'une table (INSERT, UPDATE,
DELETE) lus par réplication logique, dans l'ordre des transactions.

    sources:
      orders_changes:
        type: postgresql_cdc
        connection:
          host: ${PG_HOST}
          port: 5432
          user: ${PG_USER}            # rôle avec l'attribut REPLICATION
          password: ${PG_PASSWORD}
          database: shop
          slot: hydra_orders          # slot de réplication (un par job)
          publication: hydra_orders   # publication qui contient la table
          create: true                # crée publication et slot s'ils manquent (défaut : true)
          snapshot: true              # 1er run : la table entière, puis les changements (défaut : true)
        extract:
          table: public.orders

Chaque ligne émise porte les colonnes de la table et trois colonnes de suivi :
- `_op` : insert, update, delete ou snapshot (lignes de l'instantané initial) ;
- `_lsn` : position du changement dans le journal (texte, ex. 0/1760BD40) ;
- `_commit_time` : heure du commit (datetime avec fuseau ; None pour snapshot).
Pour un delete, seules les colonnes de la clé sont renseignées (identité de
réplication par défaut).

Une destination PostgreSQL en `mode: upsert` reconnaît `_op` : elle supprime les
lignes marquées delete, met à jour ou insère les autres, et n'écrit pas les
colonnes de suivi. En `append`, tout est écrit tel quel (un journal des changements).

Confirmation : les changements sont lus sans être consommés
(pg_logical_slot_peek_binary_changes) ; le slot n'avance (pg_replication_slot_advance)
qu'après la publication réussie de la destination. Une panne en plein chargement
fait relire les mêmes changements au run suivant : rien n'est perdu, et l'upsert
les applique sans doublon.

Prérequis côté base : wal_level = logical, PostgreSQL 11 ou plus, un rôle avec
REPLICATION (et le droit de créer la publication si `create: true`). Le pilote :
pip install "hydra-etl[postgres]".
"""

from __future__ import annotations

import datetime as _dt
import decimal
import json
import logging
import re
import struct
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

from hydra_etl.internal.connector.interface import Batch, Connector

logger = logging.getLogger(__name__)

CDC_COLUMNS = ("_op", "_lsn", "_commit_time")


class _Unchanged:
    """Valeur TOAST non modifiée par un UPDATE (le journal ne la contient pas)."""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "<unchanged>"


UNCHANGED = _Unchanged()

_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")
_TZ_RE = re.compile(r"([+-]\d{2})(?::?(\d{2}))?(?::?(\d{2}))?$")


def _parse_ts(text: str, tz: bool) -> Any:
    t = text.strip()
    if t in ("infinity", "-infinity"):
        return t
    if " BC" in t:
        return t
    t = t.replace(" ", "T", 1)
    if tz:
        m = _TZ_RE.search(t)
        if m:
            t = t[:m.start()] + f"{m.group(1)}:{m.group(2) or '00'}"
    # fromisoformat (3.9, 3.10) n'accepte que 0, 3 ou 6 décimales
    m = re.search(r"\.(\d+)", t)
    if m and len(m.group(1)) not in (3, 6):
        t = t[:m.start()] + "." + m.group(1)[:6].ljust(6, "0") + t[m.end():]
    return _dt.datetime.fromisoformat(t)


def _convert(oid: int, text: str) -> Any:
    """Valeur texte du protocole pgoutput → valeur Python selon le type PostgreSQL."""
    if oid in (20, 21, 23, 26):                       # int8, int2, int4, oid
        return int(text)
    if oid == 1700:                                   # numeric
        return decimal.Decimal(text)
    if oid in (700, 701):                             # float4, float8
        return float(text)
    if oid == 16:                                     # bool
        return text == "t"
    if oid == 1082:                                   # date
        return _dt.date.fromisoformat(text) if re.match(r"^\d{4}-\d{2}-\d{2}$", text) else text
    if oid == 1114:                                   # timestamp
        return _parse_ts(text, tz=False)
    if oid == 1184:                                   # timestamptz
        return _parse_ts(text, tz=True)
    if oid in (114, 3802):                            # json, jsonb
        return json.loads(text)
    if oid == 17 and text.startswith("\\x"):          # bytea (hex)
        return bytes.fromhex(text[2:])
    return text                                       # text, varchar, uuid, time, tableaux…


class _Reader:
    """Décodeur des messages pgoutput (protocole version 1)."""

    def __init__(self, data: bytes) -> None:
        self.b = data
        self.i = 0

    def byte(self) -> str:
        c = chr(self.b[self.i])
        self.i += 1
        return c

    def int8(self) -> int:
        v = self.b[self.i]
        self.i += 1
        return v

    def int16(self) -> int:
        v = struct.unpack_from(">h", self.b, self.i)[0]
        self.i += 2
        return v

    def int32(self) -> int:
        v = struct.unpack_from(">i", self.b, self.i)[0]
        self.i += 4
        return v

    def int64(self) -> int:
        v = struct.unpack_from(">q", self.b, self.i)[0]
        self.i += 8
        return v

    def string(self) -> str:
        end = self.b.index(0, self.i)
        s = self.b[self.i:end].decode("utf-8")
        self.i = end + 1
        return s

    def tuple(self, oids: List[int]) -> List[Any]:
        n = self.int16()
        out: List[Any] = []
        for k in range(n):
            kind = self.byte()
            if kind == "n":
                out.append(None)
            elif kind == "u":
                out.append(UNCHANGED)
            elif kind in ("t", "b"):
                size = self.int32()
                raw = self.b[self.i:self.i + size]
                self.i += size
                oid = oids[k] if k < len(oids) else 25
                out.append(_convert(oid, raw.decode("utf-8")) if kind == "t" else bytes(raw))
            else:
                raise ValueError(f"unknown tuple value kind '{kind}'")
        return out


_PG_EPOCH = _dt.datetime(2000, 1, 1, tzinfo=_dt.timezone.utc)


def _lsn_text(v: int) -> str:
    return f"{v >> 32:X}/{v & 0xFFFFFFFF:X}"


class PostgreSQLCDCConnector(Connector):
    """Source PostgreSQL CDC (réplication logique, plugin pgoutput)."""

    def __init__(self, name: str, config: Dict[str, Any]) -> None:
        super().__init__(name=name, config=config)
        conn = config.get("connection")
        if not isinstance(conn, dict):
            raise ValueError(f"PostgreSQLCDCConnector [{self.name}]: 'connection' must be a mapping")
        self._conn_cfg = dict(conn)
        for k in ("user", "database", "slot", "publication"):
            if not self._conn_cfg.get(k):
                raise ValueError(f"PostgreSQLCDCConnector [{self.name}]: connection.{k} is required")
        for k in ("slot", "publication"):
            if not re.match(r"^[a-z_][a-z0-9_]{0,62}$", str(self._conn_cfg[k])):
                raise ValueError(
                    f"PostgreSQLCDCConnector [{self.name}]: connection.{k} must be lowercase letters, "
                    f"digits and '_' (got '{self._conn_cfg[k]}')")
        self.slot = str(self._conn_cfg["slot"])
        self.publication = str(self._conn_cfg["publication"])
        self.create = _flag(self._conn_cfg.get("create"), True)
        self.snapshot = _flag(self._conn_cfg.get("snapshot"), True)
        self._pending_lsn: Optional[str] = None

    # ── Connexion ────────────────────────────────────────────────────────
    def _connect(self):
        try:
            import psycopg2  # type: ignore
        except ImportError as e:
            raise ValueError(f"PostgreSQLCDCConnector [{self.name}]: driver missing. "
                             f"Install it with 'pip install \"hydra-etl[postgres]\"'.") from e
        c = self._conn_cfg
        try:
            return psycopg2.connect(host=c.get("host", "127.0.0.1"), port=int(c.get("port", 5432)),
                                    user=c.get("user"), password=c.get("password"),
                                    dbname=c.get("database"))
        except Exception as e:
            raise ValueError(f"PostgreSQLCDCConnector [{self.name}]: database connection failed.\n"
                             f"  DSN : {self._build_connection_string()}\n"
                             f"  Error: {type(e).__name__}: {e}") from e

    def _build_connection_string(self) -> str:
        c = self._conn_cfg
        return (f"postgresql://{c.get('user')}:***@{c.get('host', '127.0.0.1')}:{c.get('port', 5432)}/"
                f"{c.get('database')}?slot={self.slot}&publication={self.publication}")

    def test_connection(self) -> None:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("SHOW wal_level")
            level = cur.fetchone()[0]
            if level != "logical":
                raise ValueError(
                    f"PostgreSQLCDCConnector [{self.name}]: wal_level is '{level}', CDC needs 'logical'. "
                    f"Run ALTER SYSTEM SET wal_level = logical; then restart PostgreSQL.")
        finally:
            conn.close()

    # ── Préparation : publication, slot ─────────────────────────────────
    @staticmethod
    def _split_table(table: str) -> Tuple[str, str]:
        parts = table.strip().split(".")
        if len(parts) == 1:
            parts = ["public", parts[0]]
        if len(parts) != 2 or not all(_NAME_RE.match(p) for p in parts):
            raise ValueError(f"invalid table name '{table}' (expected table or schema.table)")
        return parts[0], parts[1]

    def _prepare(self, cur, schema: str, table: str) -> bool:
        """Vérifie (ou crée) publication et slot. Renvoie True si le slot vient d'être créé."""
        cur.execute("SHOW wal_level")
        level = cur.fetchone()[0]
        if level != "logical":
            raise ValueError(
                f"PostgreSQLCDCConnector [{self.name}]: wal_level is '{level}', CDC needs 'logical'. "
                f"Run ALTER SYSTEM SET wal_level = logical; then restart PostgreSQL.")
        cur.execute("SELECT 1 FROM pg_publication WHERE pubname = %s", (self.publication,))
        if cur.fetchone() is None:
            if not self.create:
                raise ValueError(f"PostgreSQLCDCConnector [{self.name}]: publication '{self.publication}' "
                                 f"does not exist. Create it: CREATE PUBLICATION {self.publication} "
                                 f"FOR TABLE {schema}.{table};")
            cur.execute(f'CREATE PUBLICATION {self.publication} FOR TABLE "{schema}"."{table}"')
        cur.execute("SELECT 1 FROM pg_publication_tables WHERE pubname = %s AND schemaname = %s "
                    "AND tablename = %s", (self.publication, schema, table))
        if cur.fetchone() is None:
            raise ValueError(f"PostgreSQLCDCConnector [{self.name}]: table {schema}.{table} is not in "
                             f"publication '{self.publication}'. Add it: ALTER PUBLICATION "
                             f"{self.publication} ADD TABLE {schema}.{table};")
        cur.execute("SELECT plugin, database FROM pg_replication_slots WHERE slot_name = %s", (self.slot,))
        row = cur.fetchone()
        if row is None:
            if not self.create:
                raise ValueError(f"PostgreSQLCDCConnector [{self.name}]: replication slot '{self.slot}' "
                                 f"does not exist. Create it: SELECT pg_create_logical_replication_slot"
                                 f"('{self.slot}', 'pgoutput');")
            cur.execute("SELECT pg_create_logical_replication_slot(%s, 'pgoutput')", (self.slot,))
            logger.info("CDC source '%s': replication slot '%s' created", self.name, self.slot)
            return True
        if row[0] != "pgoutput":
            raise ValueError(f"PostgreSQLCDCConnector [{self.name}]: slot '{self.slot}' uses the plugin "
                             f"'{row[0]}'; this source needs a pgoutput slot")
        return False

    # ── Lecture ──────────────────────────────────────────────────────────
    def extract_batches(self, *, query: Optional[str] = None, table: Optional[str] = None,
                        batch_size: int = 10_000,
                        incremental: Optional[Dict[str, Any]] = None) -> Iterator[Batch]:
        if query:
            raise ValueError(f"PostgreSQLCDCConnector [{self.name}]: a CDC source reads a table "
                             f"(extract.table), not a query")
        if not table:
            raise ValueError(f"PostgreSQLCDCConnector [{self.name}]: extract.table is required")
        schema, name = self._split_table(table)
        self._pending_lsn = None
        conn = self._connect()
        try:
            conn.autocommit = True
            cur = conn.cursor()
            created = self._prepare(cur, schema, name)
            if created and self.snapshot:
                yield from self._snapshot(conn, schema, name, batch_size)
            yield from self._changes(conn, schema, name, batch_size)
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass

    def _snapshot(self, conn, schema: str, table: str, batch_size: int) -> Iterator[Batch]:
        """Premier run : la table entière (lignes _op = snapshot). Les changements faits
        depuis la création du slot sont relus ensuite : appliqués en upsert, ils
        aboutissent au même état final."""
        import psycopg2.extras  # type: ignore
        conn.autocommit = False
        try:
            cur = conn.cursor(name=f"hydra_snap_{self.slot}", cursor_factory=psycopg2.extras.RealDictCursor)
            cur.itersize = batch_size
            cur.execute(f'SELECT * FROM "{schema}"."{table}"')
            while True:
                rows = cur.fetchmany(batch_size)
                if not rows:
                    break
                yield [{**dict(r), "_op": "snapshot", "_lsn": None, "_commit_time": None} for r in rows]
            cur.close()
        finally:
            conn.rollback()
            conn.autocommit = True

    def _changes(self, conn, schema: str, table: str, batch_size: int) -> Iterator[Batch]:
        conn.autocommit = False
        relations: Dict[int, Tuple[str, str, List[str], List[int]]] = {}
        commit_time: Optional[_dt.datetime] = None
        txn: Batch = []
        buf: Batch = []
        last_end: Optional[int] = None
        try:
            cur = conn.cursor(name=f"hydra_cdc_{self.slot}")
            cur.itersize = 2000
            cur.execute(
                "SELECT lsn::text, data FROM pg_logical_slot_peek_binary_changes(%s, NULL, NULL, "
                "'proto_version', '1', 'publication_names', %s)", (self.slot, self.publication))
            for lsn, data in cur:
                r = _Reader(bytes(data))
                kind = r.byte()
                if kind == "B":
                    r.int64()                                         # LSN final de la transaction
                    ts = r.int64()
                    commit_time = _PG_EPOCH + _dt.timedelta(microseconds=ts)
                    txn = []
                elif kind == "C":
                    r.int8()
                    r.int64()                                         # LSN du commit
                    last_end = r.int64()                              # LSN de fin : reprise après lui
                    buf.extend(txn)                                   # une transaction n'est émise qu'entière
                    txn = []
                    if len(buf) >= batch_size:
                        yield buf
                        buf = []
                elif kind == "R":
                    relid = r.int32()
                    ns, rel = r.string(), r.string()
                    r.int8()                                          # identité de réplication
                    cols, oids = [], []
                    for _ in range(r.int16()):
                        r.int8()
                        cols.append(r.string())
                        oids.append(r.int32())
                        r.int32()
                    relations[relid] = (ns, rel, cols, oids)
                elif kind in ("I", "U", "D"):
                    relid = r.int32()
                    ns, rel, cols, oids = relations[relid]
                    if (ns, rel) != (schema, table):
                        continue
                    marker = r.byte()
                    if kind == "U" and marker in ("K", "O"):           # ancienne version (clé changée)
                        r.tuple(oids)
                        marker = r.byte()
                    values = r.tuple(oids)
                    op = {"I": "insert", "U": "update", "D": "delete"}[kind]
                    row: Dict[str, Any] = dict(zip(cols, values))
                    if kind == "D" and marker == "K":
                        # identité de réplication par défaut : seules les colonnes de la clé
                        row = {c: (v if v is not None else None) for c, v in row.items()}
                    row.update({"_op": op, "_lsn": lsn, "_commit_time": commit_time})
                    txn.append(row)
                # T (truncate), Y (type), O (origine) : ignorés
            cur.close()
            if buf:
                yield buf
        finally:
            try:
                conn.rollback()
            except Exception:  # noqa: BLE001
                pass
            conn.autocommit = True
        self._pending_lsn = _lsn_text(last_end) if last_end is not None else None

    # ── Confirmation après chargement réussi ─────────────────────────────
    def confirm_extract(self) -> Optional[str]:
        """Avance le slot jusqu'au dernier commit lu. Appelé par le job après la
        publication réussie de la destination. Renvoie le LSN confirmé (ou None)."""
        lsn = self._pending_lsn
        if not lsn:
            return None
        conn = self._connect()
        try:
            conn.autocommit = True
            cur = conn.cursor()
            cur.execute("SELECT pg_replication_slot_advance(%s, %s::pg_lsn)", (self.slot, lsn))
            cur.fetchall()
        finally:
            conn.close()
        self._pending_lsn = None
        logger.info("CDC source '%s': slot '%s' confirmed up to %s", self.name, self.slot, lsn)
        return lsn

    # ── Écriture : refusée ───────────────────────────────────────────────
    def load_batches(self, batches: Iterable[Batch], *, table: str, mode: str = "append",
                     key: Optional[List[str]] = None, **_: Any) -> None:
        raise ValueError(f"PostgreSQLCDCConnector [{self.name}]: a CDC source cannot be a destination; "
                         f"use type: postgresql")

    def begin_load(self, **_: Any):
        raise ValueError(f"PostgreSQLCDCConnector [{self.name}]: a CDC source cannot be a destination; "
                         f"use type: postgresql")


def _flag(v: Any, default: bool) -> bool:
    if v is None or v == "":
        return default
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "yes", "on")
