"""Mesure d'une source pour les déclencheurs `source_change`.

La source est construite exactement comme au run (job, paramètres, secrets,
environnement). La mesure ne lit que ce qu'il faut :

- base SQL (PostgreSQL, MySQL/MariaDB, SQL Server) : `SELECT COUNT(*)` ou
  `SELECT MAX(col)` sur la table ou la requête de `extract` ;
- fichier (CSV, JSON, Parquet) avec `check: checksum` : empreinte du fichier ;
- sinon (MongoDB, API web, autres cas) : lecture des lignes par lots.

Rend une chaîne (comparée à la mesure précédente) ; lève SourceMeasureError.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Optional

SQL_TYPES = ("postgresql", "postgres", "mysql", "mariadb", "sqlserver", "mssql")
FILE_TYPES = ("csv", "json", "parquet")
_COLUMN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class SourceMeasureError(RuntimeError):
    """La source n'a pas pu être mesurée (message prêt à afficher)."""


def _short(e: BaseException) -> str:
    return " ".join(str(e).split())[:160] or type(e).__name__


def _source(root: Path, job: str, source_id: str, env: Optional[str]):
    from hydra_etl.internal.runner.executor import JobExecutor
    job_dir = (Path(root) / job).resolve()
    ex = JobExecutor(job_dir=job_dir, root_dir=Path(root), env=env, params={})
    cfg = ex._source_parser.parse(ex._load_yaml_with_resolution(ex._sources_file, required=True))
    d = ex._get_source_def(cfg, source_id)
    conn = ex._build_connector(source_id, d, is_source=True)
    table, batch, query = ex._source_extract_params(d, connector=conn)
    return conn, str(getattr(d, "type", "")).lower(), table, batch, query, job_dir


def _sql(conn: Any, ctype: str, table: Optional[str], query: Optional[str],
         check: str, column: Optional[str]) -> str:
    what = "COUNT(*)" if check == "count" else f"MAX({column})"
    src = f"({query}) hydra_q" if query else table
    if not src:
        raise SourceMeasureError("the source has neither table nor query in extract")
    sql = f"SELECT {what} FROM {src}"
    c = conn._connect()
    try:
        cur = c.cursor()
        cur.execute(sql)
        row = cur.fetchone()
        cur.close()
    finally:
        try:
            c.close()
        except Exception:  # noqa: BLE001
            pass
    v = row[0] if row else None
    return "" if v is None else str(v)


def _file_checksum(job_dir: Path, conn: Any, table: Optional[str]) -> Optional[str]:
    """Empreinte du (des) fichier(s) de la source ; None si introuvable ici."""
    if not table:
        return None
    base = Path(getattr(conn, "base_path", None) or job_dir)
    target = Path(table) if Path(table).is_absolute() else base / table
    files = sorted(target.parent.glob(target.name)) if any(ch in table for ch in "*?[") else [target]
    files = [f for f in files if f.is_file()]
    if not files:
        return None
    h = hashlib.sha256()
    for f in files:
        h.update(f.name.encode())
        with f.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
    return h.hexdigest()[:16]


def _key(v: Any) -> tuple:
    """Ordre de MAX : nombres (même écrits en texte, comme dans un CSV), puis dates/texte."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return (0, float(v), "")
    try:
        return (0, float(str(v)), "")
    except ValueError:
        return (1, 0.0, str(v))


def _scan(conn: Any, table: Optional[str], query: Optional[str], batch: int,
          check: str, column: Optional[str]) -> str:
    n, best, h = 0, None, hashlib.sha256()
    for rows in conn.extract_batches(table=table, query=query, batch_size=batch):
        for r in rows:
            n += 1
            if check == "max":
                if column not in r:
                    raise SourceMeasureError(f"column '{column}' not found in the source")
                v = r[column]
                if v is not None and v != "" and (best is None or _key(v) > _key(best)):
                    best = v
            elif check == "checksum":
                h.update(json.dumps(r, sort_keys=True, default=str).encode())
    if check == "count":
        return str(n)
    if check == "max":
        return "" if best is None else str(best)
    return h.hexdigest()[:16]


def measure(root: Path, source: Any, env: Optional[str] = None) -> str:
    """Valeur courante de la source d'un déclencheur source_change (`source`: SourceRef)."""
    check, column = source.check, source.column
    if column is not None and not _COLUMN_RE.match(column):
        raise SourceMeasureError(f"column '{column}': letters, digits and '_' only")
    try:
        conn, ctype, table, batch, query, job_dir = _source(root, source.job, source.id, env)
    except SourceMeasureError:
        raise
    except Exception as e:  # noqa: BLE001 — config, paramètre, secret…
        raise SourceMeasureError(f"source '{source.id}' of {source.job}: {_short(e)}") from None
    try:
        if ctype in SQL_TYPES and check in ("count", "max") and hasattr(conn, "_connect"):
            return _sql(conn, ctype, table, query, check, column)
        if ctype in FILE_TYPES and check == "checksum":
            got = _file_checksum(job_dir, conn, table)
            if got is not None:
                return got
        return _scan(conn, table, query, batch, check, column)
    except SourceMeasureError:
        raise
    except Exception as e:  # noqa: BLE001 — base injoignable, fichier absent…
        raise SourceMeasureError(f"source '{source.id}': {_short(e)}") from None
