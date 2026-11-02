"""
workflow/subprojects.py — Projets appelés par un step `type: project`.

Un workflow d'un projet « maître » peut lancer un autre projet (« esclave ») :

    - name: load_crm
      type: project
      project: ../crm-sync      # ref: path (défaut) — relatif à la racine du maître
      # project: crm-sync       # ref: name — projet du workspace Studio

Ce module :
- résout la référence vers le dossier du projet appelé ;
- construit le graphe des appels (en suivant les workflows de chaque projet
  appelé, récursivement) et y cherche les **cycles** (A → B → A, un projet qui
  s'appelle lui-même) et les chaînes trop profondes.

Il ne lance rien : l'exécution vient avec les lots suivants.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

MAX_DEPTH = 5                      # profondeur maximale maître → esclave → …
WORKSPACE_ENV = "HYDRA_WORKSPACE"
_INDEX_NAME = "projects.index.json"


class ProjectRefError(ValueError):
    """Référence de projet introuvable ou ambiguë."""


# ── Résolution ─────────────────────────────────────────────────────────────

def workspace_dir() -> Path:
    return Path(os.environ.get(WORKSPACE_ENV) or (Path.home() / "hydra-workspace")).expanduser()


def _project_name(root: Path) -> str:
    try:
        meta = json.loads((root / ".hydra" / "project.json").read_text(encoding="utf-8-sig"))
        if isinstance(meta, dict) and meta.get("name"):
            return str(meta["name"])
    except Exception:  # noqa: BLE001
        pass
    return root.name


def workspace_projects() -> Dict[str, List[Path]]:
    """Projets connus du workspace Studio : nom -> dossiers (index + sous-dossiers)."""
    from hydra_etl.workflow.project import is_project_root
    ws = workspace_dir()
    roots: List[Path] = []
    try:
        idx = json.loads((ws / _INDEX_NAME).read_text(encoding="utf-8"))
        roots += [Path(p) for p in (idx.values() if isinstance(idx, dict) else [])]
    except Exception:  # noqa: BLE001
        pass
    if ws.is_dir():
        roots += [d for d in ws.iterdir() if d.is_dir()]
    out: Dict[str, List[Path]] = {}
    seen = set()
    for r in roots:
        try:
            r = r.resolve()
        except OSError:
            continue
        if r in seen or not is_project_root(r):
            continue
        seen.add(r)
        out.setdefault(_project_name(r), []).append(r)
    return out


def resolve_project(ref_value: str, master_root: Path, ref: Optional[str] = None) -> Path:
    """Dossier du projet appelé. ref: path (défaut) = relatif à la racine du
    maître (portable avec git) ; ref: name = nom d'un projet du workspace."""
    from hydra_etl.workflow.project import is_project_root
    value = str(ref_value).strip()
    if (ref or "path") == "name":
        found = workspace_projects().get(value, [])
        if not found:
            raise ProjectRefError(f"no project named '{value}' in the workspace "
                                  f"({workspace_dir()}); open it in Hydra Studio or use ref: path")
        if len(found) > 1:
            raise ProjectRefError(f"several projects are named '{value}' in the workspace: "
                                  + ", ".join(str(p) for p in found) + " — use ref: path")
        return found[0]
    p = Path(value).expanduser()
    p = (p if p.is_absolute() else Path(master_root) / p).resolve()
    if not p.is_dir():
        raise ProjectRefError(f"project folder not found: {value} (resolved from the project "
                              f"root: {p})")
    if not is_project_root(p):
        raise ProjectRefError(f"{value} is not a Hydra project (no .hydra/ folder in {p})")
    return p


# ── Graphe des appels ──────────────────────────────────────────────────────

@dataclass
class ProjectCall:
    workflow: str                 # workflow du projet appelant
    step: str
    value: str                    # valeur écrite dans `project:`
    ref: str                      # path | name
    workflows: Optional[List[str]] = None
    target: Optional[Path] = None
    error: Optional[str] = None
    dynamic: bool = False         # contient {{ … }} ou ${…} : résolu seulement au run


def _run_workflows(root: Path, only: Optional[List[str]]) -> List[str]:
    """Workflows qu'un run du projet lance : `only`, sinon thread.yaml (actifs
    et remplaçants), sinon tous les workflows."""
    from hydra_etl.workflow.project import resolve_thread
    if only:
        return list(only)
    try:
        thread, _ = resolve_thread(root)
    except Exception:  # noqa: BLE001 — thread invalide : signalé par prepare_project
        return []
    names: List[str] = []
    for stage in thread.thread:
        for w in stage.workflows:
            if not w.active:
                continue
            names.append(w.name)
            if w.fallback:
                names += list(w.fallback.use)
    return list(dict.fromkeys(names))


def _raw_steps(path: Path) -> List[Dict[str, Any]]:
    import yaml
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8-sig")) or {}
    except Exception:  # noqa: BLE001
        return []
    wf = doc.get("workflow") if isinstance(doc, dict) else None
    steps = (wf or {}).get("steps") if isinstance(wf, dict) else None
    return [s for s in steps or [] if isinstance(s, dict)]


def project_calls(root: Path, workflows: Optional[List[str]] = None) -> List[ProjectCall]:
    """Steps `type: project` (actifs) des workflows qu'un run de `root` lancerait."""
    from hydra_etl.workflow.project import workflow_file
    root = Path(root).resolve()
    out: List[ProjectCall] = []
    for wname in _run_workflows(root, workflows):
        for s in _raw_steps(workflow_file(root, wname)):
            if s.get("type") != "project" or s.get("enabled") is False:
                continue
            value = str(s.get("project") or "")
            ref = str(s.get("ref") or "path")
            call = ProjectCall(workflow=wname, step=str(s.get("name") or "?"), value=value, ref=ref,
                               workflows=s.get("workflows") if isinstance(s.get("workflows"), list) else None)
            if "{{" in value or "${" in value:
                call.dynamic = True
            elif value:
                try:
                    call.target = resolve_project(value, root, ref)
                except ProjectRefError as e:
                    call.error = str(e)
            out.append(call)
    return out


@dataclass
class CallCheck:
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    tree: List[Tuple[int, str]] = field(default_factory=list)   # (profondeur, libellé) pour l'affichage


def check_project_calls(root: Path, workflows: Optional[List[str]] = None,
                        max_depth: int = MAX_DEPTH) -> CallCheck:
    """Parcourt l'arbre des projets appelés depuis `root` : références
    introuvables, cycles, profondeur. Chaque problème est signalé une fois.

    Un nœud du graphe est (projet, workflows lancés) : un projet peut lancer
    un autre de ses workflows, ou être appelé deux fois avec des workflows
    différents, sans boucle. Le même nœud deux fois sur un chemin = cycle."""
    root = Path(root).resolve()
    res = CallCheck()
    seen_msgs = set()

    def add(kind: List[str], msg: str) -> None:
        if msg not in seen_msgs:
            seen_msgs.add(msg)
            kind.append(msg)

    def node(proj: Path, only: Optional[List[str]]) -> Tuple[Path, Tuple[str, ...]]:
        return (proj, tuple(sorted(_run_workflows(proj, only))))

    def label(n: Tuple[Path, Tuple[str, ...]], explicit: bool) -> str:
        return _project_name(n[0]) + (f" [{', '.join(n[1])}]" if explicit else "")

    def walk(cur: Tuple[Path, Tuple[str, ...]], only: Optional[List[str]],
             stack: List[Tuple[Path, Tuple[str, ...]]], names: List[str], depth: int) -> None:
        proj = cur[0]
        for c in project_calls(proj, only):
            where = f"{_project_name(proj)} › workflows/{c.workflow}.yaml › step '{c.step}'"
            if c.error:
                add(res.errors, f"{where}: {c.error}")
                continue
            if c.dynamic:
                add(res.warnings, f"{where}: project '{c.value}' is computed at run time; "
                                  f"cycles through it are only stopped while running")
                continue
            if c.target is None:
                continue
            nxt = node(c.target, c.workflows)
            lbl = label(nxt, bool(c.workflows))
            res.tree.append((depth, lbl))
            chain = names + [lbl]
            if nxt in stack:
                i = stack.index(nxt)
                if nxt == cur and i == len(stack) - 1:
                    add(res.errors, f"{where}: the project calls itself")
                else:
                    add(res.errors, f"{where}: cycle: " + " → ".join(chain[i:]))
                continue
            if depth >= max_depth:
                add(res.errors, f"{where}: projects nested more than {max_depth} levels deep: "
                                + " → ".join(chain))
                continue
            walk(nxt, c.workflows, stack + [nxt], chain, depth + 1)

    start = node(root, workflows)
    walk(start, workflows, [start], [label(start, False)], 1)
    return res


# ── Exécution d'un step type: project ──────────────────────────────────────
# Pile des projets appelants, transmise aux processus enfants (isolation:
# subprocess) : [[racine, [workflows]], …].
STACK_ENV = "HYDRA_PROJECT_STACK"


def _key(root: Path, workflows: Optional[List[str]]) -> List[Any]:
    root = Path(root).resolve()
    return [str(root), sorted(_run_workflows(root, workflows))]


def stack_from_env() -> List[Any]:
    try:
        v = json.loads(os.environ.get(STACK_ENV) or "[]")
        return v if isinstance(v, list) else []
    except ValueError:
        return []


def missing_required(target: Path, env: Optional[str], params: Dict[str, Any]) -> List[str]:
    """Paramètres `required` de l'esclave sans valeur (ni défaut, ni
    environnement, ni params du step)."""
    from hydra_etl.internal.config.env_admin import EnvAdminError, read_parameters
    try:
        view = read_parameters(target)
    except EnvAdminError:
        return []
    env_vals = view.environments.get(env, {}) if env else {}
    out = []
    for name, d in view.declarations.items():
        if not isinstance(d, dict) or not d.get("required"):
            continue
        if d.get("default") is not None or name in params or env_vals.get(name) is not None:
            continue
        out.append(name)
    return out


def _variables_file(variables: Dict[str, Any]) -> Optional[Path]:
    """Variables prêtées par le step : un fichier --env-file temporaire (la
    couche la plus forte dans l'esclave), supprimé après le run."""
    if not variables:
        return None
    import tempfile
    from hydra_etl.internal.config.env_admin import _format_env_value
    fd, name = tempfile.mkstemp(prefix="hydra_vars_", suffix=".env")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        for k, v in variables.items():
            f.write(f"{k}={_format_env_value('' if v is None else v)}\n")
    return Path(name)


def run_project_step(step: Any, resolved: Dict[str, Any], *, caller_root: Path,
                     caller_env: Optional[str], call_stack: List[Any], parallel: bool,
                     log: Any) -> Tuple[bool, Optional[str], List[str]]:
    """Lance le projet d'un step type: project. Retourne (succès, erreur, lignes)."""
    try:
        target = resolve_project(str(resolved.get("project") or ""), caller_root, step.ref)
    except ProjectRefError as e:
        return False, str(e), []
    params = dict(resolved.get("params") or {})
    variables = dict(resolved.get("variables") or {})
    env = caller_env if step.env in (None, "inherit") else (None if step.env == "none" else step.env)

    stack = [list(x) for x in (call_stack or [])] or [_key(caller_root, None)]
    key = _key(target, step.workflows)
    names = [_project_name(Path(p)) for p, _ in stack]
    if key in stack:
        i = stack.index(key)
        return False, "cycle: " + " → ".join(names[i:] + [_project_name(target)]) \
            + " (the project is already running in this chain)", []
    if len(stack) > MAX_DEPTH:
        return False, (f"projects nested more than {MAX_DEPTH} levels deep: "
                       + " → ".join(names + [_project_name(target)])), []
    missing = missing_required(target, env, params)
    if missing:
        return False, (f"project {_project_name(target)}: required parameter(s) without a value: "
                       f"{', '.join(missing)} — give them in params:"), []

    isolation = step.isolation or "inprocess"
    if isolation == "inprocess" and parallel:
        isolation = "subprocess"
        log.info(f"[{step.name}] runs in parallel with other steps: project "
                 f"{_project_name(target)} runs in a separate process")
    log.info(f"[{step.name}] project {_project_name(target)} ({target}) — env: {env or 'none'}, "
             f"{isolation}")
    new_stack = stack + [key]
    vfile = _variables_file(variables)
    try:
        if isolation == "subprocess":
            return _run_subprocess(step, target, env, params, vfile, new_stack, log)
        return _run_inprocess(step, target, env, params, vfile, new_stack, log)
    finally:
        if vfile is not None:
            try:
                vfile.unlink()
            except OSError:
                pass


def _summary(result: Any) -> Tuple[List[str], Optional[str]]:
    lines, first_error = [], None
    for r in result.runs:
        status = getattr(r, "status", "?")
        line = f"{r.name}: {status} ({getattr(r, 'duration', 0.0):.1f}s)"
        if getattr(r, "error", None):
            line += f" — {r.error}"
            first_error = first_error or f"{r.name}: {r.error}"
        lines.append(line)
        res = getattr(r, "result", None)
        for st in getattr(res, "steps", None) or []:
            for o in getattr(st, "output", None) or []:
                lines.append(f"  {st.step_name} │ {o}")
    return lines, first_error


def _run_inprocess(step: Any, target: Path, env: Optional[str], params: Dict[str, Any],
                   vfile: Optional[Path], stack: List[Any], log: Any
                   ) -> Tuple[bool, Optional[str], List[str]]:
    from hydra_etl.internal.config.loader import ENV_FILE_ENV, isolated_environ
    from hydra_etl.workflow.project import ProjectError, ProjectRunner, prepare_project
    overrides: Dict[str, Optional[str]] = {"HYDRA_ENV": env, ENV_FILE_ENV: str(vfile) if vfile else None,
                                           STACK_ENV: json.dumps(stack)}
    with isolated_environ(overrides):
        try:
            plan = prepare_project(target, only=step.workflows)
        except ProjectError as e:
            return False, f"project {_project_name(target)}: " + "; ".join(e.errors), list(e.errors)
        result = ProjectRunner(plan, env=env, params=params, call_stack=stack).run()
    lines, err = _summary(result)
    for ln in lines:
        log.info(f"  {ln}")
    if result.success:
        return True, None, lines
    return False, f"project {_project_name(target)} failed — {err or 'see its run'}", lines


def _run_subprocess(step: Any, target: Path, env: Optional[str], params: Dict[str, Any],
                    vfile: Optional[Path], stack: List[Any], log: Any
                    ) -> Tuple[bool, Optional[str], List[str]]:
    import subprocess
    import sys
    from hydra_etl.internal.config.loader import ENV_FILE_ENV, environ_without_layers
    cmd = [sys.executable, "-m", "hydra_etl.cli.hdrctl", "run", str(target)]
    if env:
        cmd += ["--env", env]
    for k, v in params.items():
        cmd += ["-P", f"{k}={v if isinstance(v, str) else json.dumps(v)}"]
    for w in step.workflows or []:
        cmd += ["-w", w]
    child = environ_without_layers()
    if env:
        child["HYDRA_ENV"] = env
    if vfile:
        child[ENV_FILE_ENV] = str(vfile)
    child[STACK_ENV] = json.dumps(stack)
    child["HYDRA_NO_BANNER"] = "1"
    child.setdefault("PYTHONIOENCODING", "utf-8")
    proc = subprocess.run(cmd, cwd=str(target), env=child, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    lines = [ln.rstrip() for ln in (proc.stdout + proc.stderr).splitlines() if ln.strip()]
    for ln in lines:
        log.info(f"  {ln}")
    if proc.returncode == 0:
        return True, None, lines
    err = next((ln.strip() for ln in reversed(lines) if "failed" in ln.lower() or "error" in ln.lower()),
               f"exit code {proc.returncode}")
    return False, f"project {_project_name(target)} failed — {err}", lines
