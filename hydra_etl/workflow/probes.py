"""
workflow/probes.py — Évaluation des conditions `fallback.when` (étape 2).

Chaque fonction du langage (`workflow/conditions.py`) est une **sonde** :
une vérification rapide faite juste avant le lancement d'un workflow, avec un
délai maximum. Les sondes ne lisent jamais de données et n'écrivent rien.

Deux issues bien distinctes :
- la sonde répond (ex. `source_available('crm_db')` → False : connexion
  refusée) → c'est la réponse à la question posée ;
- la sonde ne peut pas répondre (délai dépassé, source non déclarée, fichier
  absent pour `file_size`…) → `ProbeError`, et la politique `on_probe_error`
  du fallback décide (par défaut : garder le workflow prévu).

Le résultat est journalisé : chaque appel garde sa valeur
(ex. `source_available('crm_db') = false (connection refused)`).
"""
from __future__ import annotations

import ast
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from hydra_etl.workflow.conditions import parse_condition

DEFAULT_TIMEOUT = float(os.environ.get("HYDRA_PROBE_TIMEOUT", "15"))
_FILE_TYPES = ("csv", "json", "parquet")


class ProbeError(RuntimeError):
    """La sonde n'a pas pu répondre (message en anglais, prêt à afficher)."""


@dataclass
class Previous:
    """Le workflow (ou l'étape parallèle) exécuté juste avant."""
    status: str = "none"     # success | failed | inactive | none
    rows: int = 0            # lignes écrites


@dataclass
class ProbeContext:
    root: Path                                   # racine du projet
    workflow_jobs: List[Path] = field(default_factory=list)   # jobs du workflow gardé
    env: Optional[str] = None
    params: Dict[str, Any] = field(default_factory=dict)
    previous: Previous = field(default_factory=Previous)
    timeout: float = DEFAULT_TIMEOUT


@dataclass
class Evaluation:
    value: bool
    details: List[str] = field(default_factory=list)   # « appel = valeur (raison) »

    @property
    def reason(self) -> str:
        return "; ".join(self.details)


# ---------------------------------------------------------------------------
# Évaluation de l'arbre
# ---------------------------------------------------------------------------

def evaluate(condition: str, ctx: ProbeContext) -> Evaluation:
    """Évalue une condition. Lève ProbeError si une sonde nécessaire ne peut
    pas répondre (`and` / `or` s'arrêtent dès que le résultat est connu)."""
    tree, _ = parse_condition(condition)
    details: List[str] = []
    value = _eval(tree.body, ctx, details)
    return Evaluation(value=bool(value), details=details)


_CMP = {
    ast.Eq: lambda a, b: a == b, ast.NotEq: lambda a, b: a != b,
    ast.Lt: lambda a, b: a < b, ast.LtE: lambda a, b: a <= b,
    ast.Gt: lambda a, b: a > b, ast.GtE: lambda a, b: a >= b,
}


def _eval(node: ast.AST, ctx: ProbeContext, details: List[str]) -> Any:
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            for v in node.values:
                if not _eval(v, ctx, details):
                    return False
            return True
        for v in node.values:
            if _eval(v, ctx, details):
                return True
        return False
    if isinstance(node, ast.UnaryOp):
        val = _eval(node.operand, ctx, details)
        return (not val) if isinstance(node.op, ast.Not) else -val
    if isinstance(node, ast.Compare):
        left = _eval(node.left, ctx, details)
        for op, comp in zip(node.ops, node.comparators):
            right = _eval(comp, ctx, details)
            try:
                ok = _CMP[type(op)](left, right)
            except TypeError:
                raise ProbeError(f"cannot compare {left!r} with {right!r}") from None
            if not ok:
                return False
            left = right
        return True
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Call):
        name = _dotted(node.func)
        arg = node.args[0].value
        value, why = _call_probe(name, arg, ctx)
        shown = "true" if value is True else "false" if value is False else value
        details.append(f"{name}('{arg}') = {shown}" + (f" ({why})" if why else ""))
        return value
    if isinstance(node, (ast.Attribute, ast.Name)):
        name = _dotted(node)
        if name == "previous.status":
            details.append(f"previous.status = {ctx.previous.status}")
            return ctx.previous.status
        if name == "previous.rows":
            details.append(f"previous.rows = {ctx.previous.rows}")
            return ctx.previous.rows
    raise ProbeError(f"cannot evaluate {ast.unparse(node)}")


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    return f"{_dotted(node.value)}.{node.attr}"      # type: ignore[attr-defined]


def _call_probe(name: str, arg: str, ctx: ProbeContext) -> "tuple[Any, str]":
    fn = PROBES[name]
    return _with_timeout(lambda: fn(arg, ctx), ctx.timeout, f"{name}('{arg}')")


def _with_timeout(fn: Callable[[], Any], timeout: float, label: str) -> Any:
    """Exécute la sonde dans un fil séparé ; au-delà du délai → ProbeError
    (le fil, démon, est abandonné : une sonde ne doit jamais bloquer le run)."""
    box: Dict[str, Any] = {}

    def target():
        try:
            box["value"] = fn()
        except BaseException as e:  # noqa: BLE001
            box["error"] = e

    th = threading.Thread(target=target, daemon=True, name=f"probe {label}")
    th.start()
    th.join(timeout)
    if th.is_alive():
        raise ProbeError(f"{label} timed out after {timeout:g}s")
    if "error" in box:
        e = box["error"]
        raise e if isinstance(e, ProbeError) else ProbeError(f"{label}: {e}")
    return box["value"]


# ---------------------------------------------------------------------------
# Sondes
# ---------------------------------------------------------------------------

def _path(arg: str, ctx: ProbeContext) -> Path:
    p = Path(arg).expanduser()
    return p if p.is_absolute() else Path(ctx.root) / p


def probe_file_exists(arg: str, ctx: ProbeContext):
    p = _path(arg, ctx)
    return p.exists(), "" if p.exists() else "not found"


def probe_file_size(arg: str, ctx: ProbeContext):
    p = _path(arg, ctx)
    if not p.is_file():
        raise ProbeError(f"file_size('{arg}'): file not found ({p})")
    return p.stat().st_size, "bytes"


def probe_file_age(arg: str, ctx: ProbeContext):
    p = _path(arg, ctx)
    if not p.exists():
        raise ProbeError(f"file_age('{arg}'): file not found ({p})")
    return round(time.time() - p.stat().st_mtime, 1), "seconds since last change"


def probe_url_ok(arg: str, ctx: ProbeContext):
    import urllib.error
    import urllib.request
    req = urllib.request.Request(arg, method="GET", headers={"User-Agent": "hydra-etl-probe"})
    try:
        with urllib.request.urlopen(req, timeout=max(1.0, ctx.timeout - 1)) as r:   # noqa: S310
            return r.status < 400, f"HTTP {r.status}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except (urllib.error.URLError, OSError) as e:
        reason = getattr(e, "reason", e)
        return False, str(reason)[:120]


def probe_secret_defined(arg: str, ctx: ProbeContext):
    from hydra_etl.internal.config.secrets import SecretResolutionError, SecretResolver, project_secrets
    try:
        SecretResolver(secrets={}, fallback=project_secrets(ctx.root))._get_secret(arg)
        return True, ""
    except SecretResolutionError:
        return False, "not in the environment nor in the secrets file"


def _find_job(kind: str, name: str, ctx: ProbeContext) -> Path:
    """Job qui déclare `name` dans sources.yaml / destinations.yaml : d'abord
    les jobs du workflow gardé, puis tous les jobs du projet."""
    import yaml
    candidates = list(ctx.workflow_jobs) + sorted(
        d for d in (Path(ctx.root) / "jobs").glob("*") if d.is_dir())
    for jd in candidates:
        f = jd / f"{kind}.yaml"
        try:
            doc = yaml.safe_load(f.read_text(encoding="utf-8-sig")) or {}
        except Exception:  # noqa: BLE001
            continue
        sec = doc.get(kind) if isinstance(doc, dict) else None
        if isinstance(sec, dict) and name in sec:
            return jd
    raise ProbeError(f"'{name}' is not declared in any job's {kind}.yaml")


def _connector(kind: str, name: str, ctx: ProbeContext):
    """(connecteur, type) construit comme à l'exécution : paramètres, secrets,
    environnement (--env) et chemins du job."""
    from hydra_etl.internal.runner.executor import JobExecutor
    job_dir = _find_job(kind, name, ctx)
    ex = JobExecutor(job_dir=job_dir, root_dir=Path(ctx.root), env=ctx.env, params=dict(ctx.params))
    if kind == "sources":
        cfg = ex._source_parser.parse(ex._load_yaml_with_resolution(ex._sources_file, required=True))
        d = ex._get_source_def(cfg, name)
        return ex._build_connector(name, d, is_source=True), str(getattr(d, "type", "")).lower(), d
    cfg = ex._dest_parser.parse(ex._load_yaml_with_resolution(ex._destinations_file, required=True))
    d = ex._get_dest_def(cfg, name)
    return ex._build_connector(name, d, is_source=False), str(getattr(d, "type", "")).lower(), d


def _short(e: BaseException) -> str:
    return " ".join(str(e).split())[:140] or type(e).__name__


def probe_source_available(arg: str, ctx: ProbeContext):
    try:
        conn, ctype, _ = _connector("sources", arg, ctx)
    except ProbeError:
        raise
    except Exception as e:  # noqa: BLE001 — fichier source absent, config…
        if "not found" in str(e).lower() or "introuvable" in str(e).lower():
            return False, _short(e)
        raise ProbeError(f"source_available('{arg}'): {_short(e)}") from None
    if ctype in _FILE_TYPES:
        # source fichier : disponible si le fichier (ou un fichier du motif) existe
        _, _, d = _connector("sources", arg, ctx)
        ext = getattr(d, "extract", None)
        table = getattr(ext, "table", None) or getattr(ext, "file", None) \
            or (ext.get("table") or ext.get("file") if isinstance(ext, dict) else None)
        if not table:
            raise ProbeError(f"source_available('{arg}'): no file path in its extract section")
        base = _find_job("sources", arg, ctx)
        target = Path(table) if Path(table).is_absolute() else base / table
        if any(ch in str(table) for ch in "*?["):
            hits = list(target.parent.glob(target.name))
            return bool(hits), f"{len(hits)} file(s) match {table}"
        return target.is_file(), "file found" if target.is_file() else f"file not found: {target}"
    try:
        conn.test_connection()
        return True, "connection OK"
    except Exception as e:  # noqa: BLE001 — injoignable = la réponse
        return False, _short(e)


def probe_destination_available(arg: str, ctx: ProbeContext):
    try:
        conn, ctype, d = _connector("destinations", arg, ctx)
    except ProbeError:
        raise
    except Exception as e:  # noqa: BLE001
        raise ProbeError(f"destination_available('{arg}'): {_short(e)}") from None
    if ctype in _FILE_TYPES:
        # une destination fichier est « disponible » si son dossier l'est
        load = getattr(d, "load", None)
        table = getattr(load, "table", None) or (load.get("table") if isinstance(load, dict) else None)
        job_dir = _find_job("destinations", arg, ctx)
        target = Path(table) if table and Path(table).is_absolute() else job_dir / (table or "")
        folder = target.parent
        while not folder.exists() and folder != folder.parent:
            folder = folder.parent                     # le dossier sera créé
        ok = os.access(folder, os.W_OK)
        return ok, f"folder {'writable' if ok else 'not writable'}: {folder}"
    try:
        conn.test_connection()
        return True, "connection OK"
    except Exception as e:  # noqa: BLE001
        return False, _short(e)


_LOAD_SQL = {
    "postgresql": "SELECT count(*) FROM pg_stat_activity WHERE state = 'active' AND pid <> pg_backend_pid()",
    "postgres":   "SELECT count(*) FROM pg_stat_activity WHERE state = 'active' AND pid <> pg_backend_pid()",
    "mysql":      "SELECT COUNT(*) FROM information_schema.PROCESSLIST WHERE COMMAND <> 'Sleep' AND ID <> CONNECTION_ID()",
    "mariadb":    "SELECT COUNT(*) FROM information_schema.PROCESSLIST WHERE COMMAND <> 'Sleep' AND ID <> CONNECTION_ID()",
    "sqlserver":  "SELECT COUNT(*) FROM sys.dm_exec_requests WHERE session_id <> @@SPID AND session_id > 50",
    "mssql":      "SELECT COUNT(*) FROM sys.dm_exec_requests WHERE session_id <> @@SPID AND session_id > 50",
}


def probe_db_load(arg: str, ctx: ProbeContext):
    """Requêtes actives sur la base (hors celle de la sonde)."""
    try:
        conn, ctype, _ = _connector("sources", arg, ctx)
    except ProbeError:
        conn, ctype, _ = _connector("destinations", arg, ctx)
    sql = _LOAD_SQL.get(ctype)
    if sql is None or not hasattr(conn, "_connect"):
        raise ProbeError(f"db.load('{arg}'): '{arg}' is a {ctype or '?'} connector, not a supported database")
    try:
        c = conn._connect()
        cur = c.cursor()
        cur.execute(sql)
        n = int(cur.fetchone()[0])
        cur.close()
        c.close()
        return n, "active queries"
    except Exception as e:  # noqa: BLE001
        raise ProbeError(f"db.load('{arg}'): {_short(e)}") from None


PROBES: Dict[str, Callable[[str, ProbeContext], Any]] = {
    "source_available": probe_source_available,
    "destination_available": probe_destination_available,
    "file_exists": probe_file_exists,
    "file_size": probe_file_size,
    "file_age": probe_file_age,
    "url_ok": probe_url_ok,
    "secret_defined": probe_secret_defined,
    "db.load": probe_db_load,
}
