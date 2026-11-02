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


Node = Tuple[Path, Tuple[str, ...]]


def _node(proj: Path, only: Optional[List[str]]) -> Node:
    return (Path(proj).resolve(), tuple(sorted(_run_workflows(Path(proj).resolve(), only))))


def _label(n: Node, explicit: bool) -> str:
    return _project_name(n[0]) + (f" [{', '.join(n[1])}]" if explicit else "")


def _walk(res: CallCheck, cur: Node, only: Optional[List[str]], stack: List[Node],
          names: List[str], depth: int, max_depth: int, seen_msgs: set) -> None:
    def add(kind: List[str], msg: str) -> None:
        if msg not in seen_msgs:
            seen_msgs.add(msg)
            kind.append(msg)

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
        nxt = _node(c.target, c.workflows)
        lbl = _label(nxt, bool(c.workflows))
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
        _walk(res, nxt, c.workflows, stack + [nxt], chain, depth + 1, max_depth, seen_msgs)


def check_project_calls(root: Path, workflows: Optional[List[str]] = None,
                        max_depth: int = MAX_DEPTH) -> CallCheck:
    """Parcourt l'arbre des projets appelés depuis `root` : références
    introuvables, cycles, profondeur. Chaque problème est signalé une fois.

    Un nœud du graphe est (projet, workflows lancés) : un projet peut lancer
    un autre de ses workflows, ou être appelé deux fois avec des workflows
    différents, sans boucle. Le même nœud deux fois sur un chemin = cycle."""
    res = CallCheck()
    start = _node(root, workflows)
    _walk(res, start, workflows, [start], [_label(start, False)], 1, max_depth, set())
    return res


def check_new_call(master_root: Path, target: Path, workflows: Optional[List[str]] = None,
                   max_depth: int = MAX_DEPTH) -> CallCheck:
    """Ce que donnerait un nouveau step type: project de `master_root` vers
    `target` (Studio, au dépôt du nœud) : cycle, profondeur, arbre."""
    res = CallCheck()
    start = _node(master_root, None)
    nxt = _node(target, workflows)
    res.tree.append((1, _label(nxt, bool(workflows))))
    if nxt[0] == start[0] and nxt == start:
        res.errors.append("the project would call itself")
        return res
    names = [_label(start, False), _label(nxt, bool(workflows))]
    _walk(res, nxt, workflows, [start, nxt], names, 2, max_depth, set())
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


@dataclass
class ProjectOutcome:
    """Résultat d'un step type: project, posé dans les paramètres runtime du
    maître : {{ project:STEP.status }}, .rows, .duration, .param.NOM."""
    success: bool
    status: str                                  # success | failed | skipped
    error: Optional[str] = None
    lines: List[str] = field(default_factory=list)
    rows: int = 0
    duration: float = 0.0
    published: Dict[str, Any] = field(default_factory=dict)


# ── Verrou : un projet appelé ne tourne qu'une fois à la fois ──────────────
import threading as _threading
import time as _time

_LOCKS: Dict[str, Any] = {}
_LOCKS_GUARD = _threading.Lock()
LOCK_FILE = "run.lock"               # .hydra/run.lock du projet appelé


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)   # QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(h)
        return bool(ok) and code.value == 259                        # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _try_file_lock(target: Path) -> bool:
    f = target / ".hydra" / LOCK_FILE
    for _ in range(2):
        try:
            fd = os.open(str(f), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                info = json.loads(f.read_text(encoding="utf-8") or "{}")
            except Exception:  # noqa: BLE001
                info = {}
            if _pid_alive(int(info.get("pid") or 0)):
                return False
            try:                                  # verrou d'un processus disparu
                f.unlink()
            except OSError:
                return False
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as h:
            json.dump({"pid": os.getpid(), "since": _time.strftime("%Y-%m-%dT%H:%M:%S")}, h)
        return True
    return False


def _release_file_lock(target: Path) -> None:
    try:
        (target / ".hydra" / LOCK_FILE).unlink()
    except OSError:
        pass


def _acquire(target: Path, mode: str, deadline: Optional[float]) -> bool:
    """Verrou du projet appelé (dans ce processus, puis entre processus).
    mode wait : attend (jusqu'à `deadline`) ; skip / fail : essai unique."""
    key = str(target)
    with _LOCKS_GUARD:
        lk = _LOCKS.setdefault(key, _threading.Lock())
    while True:
        if lk.acquire(blocking=False):
            if _try_file_lock(target):
                return True
            lk.release()
        if mode != "wait" or (deadline is not None and _time.monotonic() >= deadline):
            return False
        _time.sleep(0.5)


def _release(target: Path) -> None:
    _release_file_lock(target)
    with _LOCKS_GUARD:
        lk = _LOCKS.get(str(target))
    if lk is not None and lk.locked():
        lk.release()


def run_project_step(step: Any, resolved: Dict[str, Any], *, caller_root: Path,
                     caller_env: Optional[str], call_stack: List[Any], parallel: bool,
                     log: Any) -> ProjectOutcome:
    """Lance le projet d'un step type: project."""
    t0 = _time.monotonic()

    def fail(msg: str, lines: Optional[List[str]] = None) -> ProjectOutcome:
        return ProjectOutcome(False, "failed", msg, lines or [], duration=_time.monotonic() - t0)

    try:
        target = resolve_project(str(resolved.get("project") or ""), caller_root, step.ref)
    except ProjectRefError as e:
        return fail(str(e))
    name = _project_name(target)
    params = dict(resolved.get("params") or {})
    variables = dict(resolved.get("variables") or {})
    env = caller_env if step.env in (None, "inherit") else (None if step.env == "none" else step.env)

    stack = [list(x) for x in (call_stack or [])] or [_key(caller_root, None)]
    key = _key(target, step.workflows)
    names = [_project_name(Path(p)) for p, _ in stack]
    if key in stack:
        i = stack.index(key)
        return fail("cycle: " + " → ".join(names[i:] + [name])
                    + " (the project is already running in this chain)")
    if len(stack) > MAX_DEPTH:
        return fail(f"projects nested more than {MAX_DEPTH} levels deep: " + " → ".join(names + [name]))
    missing = missing_required(target, env, params)
    if missing:
        return fail(f"project {name}: required parameter(s) without a value: "
                    f"{', '.join(missing)} — give them in params:")

    from hydra_etl.workflow.thread import parse_delay
    timeout = parse_delay(step.timeout) if step.timeout is not None else None
    overlap = step.overlap or "wait"
    deadline = (t0 + timeout) if timeout else None
    if not _acquire(target, overlap, deadline):
        msg = f"project {name} is already running"
        if overlap == "skip":
            log.info(f"[{step.name}] {msg}: step skipped (overlap: skip)")
            return ProjectOutcome(True, "skipped", None, [f"{msg} — skipped (overlap: skip)"],
                                  duration=_time.monotonic() - t0)
        return fail(f"{msg} (overlap: {overlap})")
    try:
        isolation = step.isolation or "inprocess"
        if isolation == "inprocess" and parallel:
            isolation = "subprocess"
            log.info(f"[{step.name}] runs in parallel with other steps: project {name} "
                     f"runs in a separate process")
        log.info(f"[{step.name}] project {name} ({target}) — env: {env or 'none'}, {isolation}")
        left = (deadline - _time.monotonic()) if deadline else None
        if left is not None and left <= 0:
            return fail(f"project {name}: timed out after {step.timeout} (waiting for its lock)")
        vfile = _variables_file(variables)
        try:
            run = _run_subprocess if isolation == "subprocess" else _run_inprocess
            out = run(step, target, env, params, vfile, stack + [key], log, left)
        finally:
            if vfile is not None:
                try:
                    vfile.unlink()
                except OSError:
                    pass
    finally:
        _release(target)
    out.duration = _time.monotonic() - t0
    # outputs : paramètres publiés par l'esclave, exigés s'il a réussi
    if out.success and step.outputs:
        absent = [o for o in step.outputs if o not in out.published]
        if absent:
            out.success, out.status = False, "failed"
            out.error = (f"project {name} did not publish {', '.join(absent)} "
                         f"(outputs: set them with set_param / assign_param, or declare them)")
    return out


def _tree(result: Any) -> Tuple[List[str], Optional[str]]:
    """Runs de l'esclave, en arbre : workflow, puis ses steps et leur sortie."""
    lines, first_error = [], None
    for r in result.runs:
        status = getattr(r, "status", "?")
        mark = {"success": "✓", "recovered": "↪", "failed": "✗"}.get(str(status), "·")
        line = f"{mark} {r.name} ({getattr(r, 'duration', 0.0):.1f}s)"
        if str(status) not in ("success",):
            line += f" — {status}"
        if getattr(r, "error", None):
            line += f": {r.error}"
            first_error = first_error or f"{r.name}: {r.error}"
        lines.append(line)
        res = getattr(r, "result", None)
        for st in getattr(res, "steps", None) or []:
            smark = "⏭" if st.skipped else ("✓" if st.success else "✗")
            lines.append(f"    {smark} {st.step_name}" + (f" — {st.error}" if st.error else ""))
            for o in getattr(st, "output", None) or []:
                lines.append(f"      │ {o}")
    return lines, first_error


def _run_inprocess(step: Any, target: Path, env: Optional[str], params: Dict[str, Any],
                   vfile: Optional[Path], stack: List[Any], log: Any,
                   timeout: Optional[float]) -> ProjectOutcome:
    from hydra_etl.internal.config.loader import ENV_FILE_ENV, isolated_environ
    from hydra_etl.workflow.project import ProjectError, ProjectRunner, _rows_written, prepare_project
    name = _project_name(target)
    overrides: Dict[str, Optional[str]] = {"HYDRA_ENV": env, ENV_FILE_ENV: str(vfile) if vfile else None,
                                           STACK_ENV: json.dumps(stack)}
    timed_out = []
    with isolated_environ(overrides):
        try:
            plan = prepare_project(target, only=step.workflows)
        except ProjectError as e:
            return ProjectOutcome(False, "failed", f"project {name}: " + "; ".join(e.errors), list(e.errors))
        runner = ProjectRunner(plan, env=env, params=params, call_stack=stack)
        timer = None
        if timeout:
            def _expire() -> None:
                timed_out.append(True)
                runner.halt(f"timed out after {step.timeout} (timeout of step '{step.name}')")
            timer = _threading.Timer(timeout, _expire)
            timer.daemon = True
            timer.start()
        try:
            result = runner.run()
        finally:
            if timer is not None:
                timer.cancel()
    lines, err = _tree(result)
    for ln in lines:
        log.info(f"  {ln}")
    rows = sum(_rows_written(r) for r in result.runs)
    if timed_out:
        return ProjectOutcome(False, "failed", f"project {name}: timed out after {step.timeout}",
                              lines, rows=rows, published=dict(runner.published))
    if result.success:
        return ProjectOutcome(True, "success", None, lines, rows=rows, published=dict(runner.published))
    return ProjectOutcome(False, "failed", f"project {name} failed — {err or 'see its run'}", lines,
                          rows=rows, published=dict(runner.published))


OUTPUTS_ENV = "HYDRA_PROJECT_OUTPUTS"      # fichier où un run enfant écrit ses résultats


def write_outputs(runner: Any, result: Any) -> None:
    """Appelé par `hdrctl run <projet>` lancé par un step (isolation: subprocess)."""
    f = os.environ.get(OUTPUTS_ENV)
    if not f:
        return
    from hydra_etl.workflow.project import _rows_written
    try:
        Path(f).write_text(json.dumps({
            "success": bool(result.success),
            "rows": sum(_rows_written(r) for r in result.runs),
            "published": getattr(runner, "published", {}),
        }, default=str), encoding="utf-8")
    except OSError:
        pass


def _run_subprocess(step: Any, target: Path, env: Optional[str], params: Dict[str, Any],
                    vfile: Optional[Path], stack: List[Any], log: Any,
                    timeout: Optional[float]) -> ProjectOutcome:
    import subprocess
    import sys
    import tempfile
    from hydra_etl.internal.config.loader import ENV_FILE_ENV, environ_without_layers
    name = _project_name(target)
    cmd = [sys.executable, "-m", "hydra_etl.cli.hdrctl", "run", str(target)]
    if env:
        cmd += ["--env", env]
    for k, v in params.items():
        cmd += ["-P", f"{k}={v if isinstance(v, str) else json.dumps(v)}"]
    for w in step.workflows or []:
        cmd += ["-w", w]
    fd, outf = tempfile.mkstemp(prefix="hydra_out_", suffix=".json")
    os.close(fd)
    child = environ_without_layers()
    if env:
        child["HYDRA_ENV"] = env
    if vfile:
        child[ENV_FILE_ENV] = str(vfile)
    child[STACK_ENV] = json.dumps(stack)
    child[OUTPUTS_ENV] = outf
    child["HYDRA_NO_BANNER"] = "1"
    child.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        try:
            proc = subprocess.run(cmd, cwd=str(target), env=child, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=timeout)
        except subprocess.TimeoutExpired as e:
            def _txt(b: Any) -> str:
                return b.decode("utf-8", "replace") if isinstance(b, bytes) else (b or "")
            out = _txt(e.stdout) + _txt(e.stderr)
            lines = [ln.rstrip() for ln in out.splitlines() if ln.strip()]
            return ProjectOutcome(False, "failed", f"project {name}: timed out after {step.timeout} "
                                  f"(process stopped)", lines)
        lines = [ln.rstrip() for ln in (proc.stdout + proc.stderr).splitlines() if ln.strip()]
        for ln in lines:
            log.info(f"  {ln}")
        try:
            data = json.loads(Path(outf).read_text(encoding="utf-8") or "{}")
        except (OSError, ValueError):
            data = {}
    finally:
        try:
            os.unlink(outf)
        except OSError:
            pass
    rows, published = int(data.get("rows") or 0), dict(data.get("published") or {})
    if proc.returncode == 0:
        return ProjectOutcome(True, "success", None, lines, rows=rows, published=published)
    err = next((ln.strip() for ln in reversed(lines) if "failed" in ln.lower() or "error" in ln.lower()),
               f"exit code {proc.returncode}")
    return ProjectOutcome(False, "failed", f"project {name} failed — {err}", lines,
                          rows=rows, published=published)
