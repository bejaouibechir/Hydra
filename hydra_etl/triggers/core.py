"""Déclencheurs de projet : contrôles, historique, lancement.

Le lancement réutilise le mécanisme des steps `type: project` (verrou
.hydra/run.lock, overlap, timeout, processus séparé) : un déclencheur est un
appel de projet dont l'appelant est l'événement."""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from hydra_etl.triggers.models import ProjectTrigger, TriggerFile, TriggerFileError, load_triggers

HISTORY_DIR = Path(".hydra") / "triggers"
HISTORY_FILE = "history.jsonl"
HISTORY_KEEP = 1000
_HISTORY_LOCK = threading.Lock()
log = logging.getLogger("hydra.triggers")


# ── Contrôles au niveau du projet ──────────────────────────────────────────

@dataclass
class TriggerCheck:
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def _source_ids(job_dir: Path) -> List[str]:
    try:
        data = yaml.safe_load((job_dir / "sources.yaml").read_text(encoding="utf-8-sig")) or {}
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return []
    src = data.get("sources") if isinstance(data, dict) else None
    return list(src) if isinstance(src, dict) else []


def _secret_known(root: Path, name: str) -> bool:
    from hydra_etl.internal.config.secrets import project_secrets
    norm = name.replace(".", "_").replace("-", "_").upper()
    if name in os.environ or norm in os.environ:
        return True
    try:
        if name in project_secrets(root, env=None):
            return True
    except Exception:  # noqa: BLE001
        return False
    sdir = Path(root) / ".hydra"
    for f in sdir.glob("secrets.*"):          # secrets d'un environnement
        if f.suffix in (".yaml", ".yml"):
            continue
        try:
            if any(line.split("=", 1)[0].strip() == name
                   for line in f.read_text(encoding="utf-8-sig").splitlines() if "=" in line):
                return True
        except (OSError, UnicodeDecodeError):
            pass
    return False


def _after_predecessors(root: Path) -> List[Path]:
    """Projets dont la fin lance `root` (ses déclencheurs after_project)."""
    from hydra_etl.workflow.subprojects import ProjectRefError, resolve_project
    try:
        tf = load_triggers(root)
    except TriggerFileError:
        return []
    out = []
    for t in tf.triggers:
        if t.type == "after_project" and t.enabled:
            try:
                out.append(resolve_project(t.project, root, t.ref))
            except ProjectRefError:
                pass
    return out


def _after_cycle(root: Path) -> Optional[List[Path]]:
    """Chaîne after_project qui revient à `root` (A → B → A), sinon None."""
    from hydra_etl.workflow.subprojects import MAX_DEPTH
    root = Path(root).resolve()
    stack: List[Path] = []

    def walk(p: Path, depth: int) -> Optional[List[Path]]:
        for prev in _after_predecessors(p):
            prev = prev.resolve()
            if prev == root:
                return [p, prev]
            if prev in stack or depth > MAX_DEPTH * 4:
                continue
            stack.append(prev)
            found = walk(prev, depth + 1)
            stack.pop()
            if found:
                return [p] + found
        return None

    return walk(root, 0)


def check_triggers(root: Path, tf: Optional[TriggerFile] = None) -> TriggerCheck:
    """Contrôles qui demandent le projet : workflows, projets appelés, jobs,
    secrets, boucles after_project. Lève TriggerFileError si le fichier est invalide."""
    from hydra_etl.workflow.project import workflow_files
    from hydra_etl.workflow.subprojects import (ProjectRefError, _project_name,
                                                 check_project_calls, resolve_project)
    root = Path(root).resolve()
    tf = tf if tf is not None else load_triggers(root)
    res = TriggerCheck()
    known = workflow_files(root)
    for t in tf.triggers:
        where = f"trigger '{t.name}'"
        missing = [w for w in (t.workflows or []) if w not in known]
        if missing:
            res.errors.append(f"{where}: workflow(s) not found: {', '.join(missing)} "
                              f"(workflows/<name>.yaml)")
            continue
        if t.enabled:
            calls = check_project_calls(root, workflows=t.workflows)
            res.errors += [f"{where}: {e}" for e in calls.errors]
        if t.type == "source_change":
            jdir = (root / t.source.job).resolve()
            if not (jdir / "sources.yaml").is_file():
                res.errors.append(f"{where}: source.job '{t.source.job}' is not a job folder "
                                  f"(no sources.yaml)")
            elif t.source.id not in _source_ids(jdir):
                res.errors.append(f"{where}: source '{t.source.id}' is not declared in "
                                  f"{t.source.job}/sources.yaml")
        if t.type == "webhook":
            name = str(t.token).strip()[len("${SECRET:"):-1]
            if not _secret_known(root, name):
                res.warnings.append(f"{where}: secret '{name}' is not set yet "
                                    f"(hdrctl secret set {name})")
        if t.type == "after_project":
            try:
                other = resolve_project(t.project, root, t.ref)
            except ProjectRefError as e:
                res.errors.append(f"{where}: {e}")
                continue
            if other.resolve() == root:
                res.errors.append(f"{where}: a project cannot be started by its own end")
    loop = _after_cycle(root)
    if loop:
        names = [_project_name(root)] + [_project_name(p) for p in loop[1:]]
        names = list(reversed(names))
        res.errors.append("after_project loop: " + " → ".join(names)
                          + " (each end would start the next one forever)")
    return res


# ── Historique ─────────────────────────────────────────────────────────────

def history_file(root: Path) -> Path:
    return Path(root) / HISTORY_DIR / HISTORY_FILE


def record(root: Path, entry: Dict[str, Any]) -> None:
    """Ajoute une ligne à .hydra/triggers/history.jsonl (garde les 1000 dernières)."""
    f = history_file(root)
    entry = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **entry}
    with _HISTORY_LOCK:
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            ign = f.parent / ".gitignore"          # historique local : jamais versionné
            if not ign.exists():
                ign.write_text("*\n", encoding="utf-8")
            with f.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
            if f.stat().st_size > 400_000:
                lines = f.read_text(encoding="utf-8").splitlines()[-HISTORY_KEEP:]
                tmp = f.with_suffix(".tmp")
                tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
                os.replace(tmp, f)
        except OSError as e:
            log.warning("trigger history not written (%s): %s", f, e)


def read_history(root: Path, trigger: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """Dernières entrées, la plus récente en dernier."""
    f = history_file(root)
    if not f.exists():
        return []
    out = []
    try:
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if trigger is None or e.get("trigger") == trigger:
                out.append(e)
    except (OSError, UnicodeDecodeError):
        return []
    return out[-limit:]


def last_runs(root: Path) -> Dict[str, Dict[str, Any]]:
    """Dernière entrée par déclencheur."""
    out: Dict[str, Dict[str, Any]] = {}
    for e in read_history(root, limit=HISTORY_KEEP):
        out[str(e.get("trigger"))] = e
    return out


# ── Lancement ──────────────────────────────────────────────────────────────

@dataclass
class FireResult:
    trigger: str
    status: str                       # success | failed | skipped
    error: Optional[str] = None
    lines: List[str] = field(default_factory=list)
    duration: float = 0.0
    attempts: int = 1


def fire(root: Path, trig: ProjectTrigger, *, origin: str = "manual", env: Optional[str] = None,
         detail: Optional[str] = None, retry: bool = True,
         stop: Optional[threading.Event] = None, logger: Any = None) -> FireResult:
    """Lance le projet comme le déclencheur `trig` : son env (sinon `env`),
    ses workflows, params, overlap, timeout ; relance après échec (`retry`).
    Toujours dans un processus séparé : plusieurs déclencheurs peuvent tourner
    en même temps dans hdrctl watch / serve."""
    from hydra_etl.workflow.models import WorkflowStep
    from hydra_etl.workflow.subprojects import run_project_step
    from hydra_etl.workflow.thread import parse_delay
    root = Path(root).resolve()
    lg = logger or log
    step = WorkflowStep(name=trig.name, type="project", project=str(root),
                        env=trig.env or "inherit", params=trig.params or None,
                        workflows=trig.workflows, timeout=trig.timeout,
                        overlap=trig.overlap, isolation="subprocess")
    attempts = 1 + (trig.retry.max if (retry and trig.retry) else 0)
    delay = parse_delay(trig.retry.delay) if trig.retry else 0.0
    t0 = time.monotonic()
    res = FireResult(trig.name, "failed")
    for attempt in range(1, attempts + 1):
        out = run_project_step(step, {"project": str(root), "params": dict(trig.params or {})},
                               caller_root=root, caller_env=env,
                               call_stack=[[f"trigger:{trig.name}", []]], parallel=True, log=lg)
        res = FireResult(trig.name, out.status if out.status in ("success", "skipped") else
                         ("success" if out.success else "failed"),
                         out.error, list(out.lines), time.monotonic() - t0, attempt)
        record(root, {"trigger": trig.name, "type": trig.type, "origin": origin,
                      "status": res.status, "attempt": attempt, "env": trig.env or env,
                      "duration": round(out.duration, 2), "error": out.error, "detail": detail})
        if res.status != "failed" or attempt == attempts:
            break
        lg.info(f"[{trig.name}] failed (attempt {attempt}/{attempts}); retry in {trig.retry.delay}")
        if stop is not None:
            if stop.wait(delay):
                break
        else:
            time.sleep(delay)
    return res
