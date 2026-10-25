"""
workflow/project.py — Exécution d'un PROJET Hydra entier.

Un projet est un ensemble de workflows ; un workflow est un ensemble de jobs et
d'actions. `hdrctl run <projet>` lance les workflows dans l'ordre fixé par
`workflows/thread.yaml` (voir workflow/thread.py) :

- les étapes (stages) s'enchaînent dans l'ordre du fichier ;
- `mode: sequential` : les workflows de l'étape tournent l'un après l'autre,
  `mode: parallel` : en même temps ;
- `delay_after` : pause avant l'étape suivante (pas après la dernière) ;
- `active: false` : workflow ignoré ;
- un workflow en échec arrête le projet : les workflows suivants ne sont pas
  lancés (dans une étape parallèle, ceux déjà partis vont à leur terme).

Sans `thread.yaml`, tous les `workflows/*.yaml` tournent l'un après l'autre,
par ordre alphabétique.

Paramètres : `parameters.yaml` et `environments/<env>.yaml` à la racine du
projet, surchargés par `--param` (voir WorkflowRunner).

Les déclencheurs `trigger` (schedule, webhook) des workflows sont ignorés ici :
`hdrctl run` exécute tout de suite. Ils servent sous `hdrctl serve`.
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from hydra_etl.workflow.thread import (
    THREAD_FILE, ThreadDef, ThreadStage, ThreadWorkflow, load_thread, missing_workflow_files,
)

PROJECT_MARKER = ".hydra"
WORKFLOWS_DIR = "workflows"


def is_project_root(path: Path) -> bool:
    return (Path(path) / PROJECT_MARKER).is_dir()


def find_project_root(start: Path, max_levels: int = 6) -> Optional[Path]:
    """Remonte depuis `start` jusqu'au premier dossier qui contient `.hydra/`."""
    d = Path(start).resolve()
    for _ in range(max_levels + 1):
        if is_project_root(d):
            return d
        if d.parent == d:
            return None
        d = d.parent
    return None


class ProjectError(ValueError):
    """Le projet ne peut pas démarrer. `errors` liste chaque problème trouvé."""

    def __init__(self, errors: List[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


def workflow_file(root: Path, name: str) -> Path:
    wdir = Path(root) / WORKFLOWS_DIR
    yml = wdir / f"{name}.yml"
    return yml if yml.is_file() and not (wdir / f"{name}.yaml").is_file() else wdir / f"{name}.yaml"


def resolve_thread(root: Path) -> Tuple[ThreadDef, bool]:
    """(thread, implicite). Sans thread.yaml : tous les workflows, l'un après
    l'autre, par ordre alphabétique (implicite = True)."""
    wdir = Path(root) / WORKFLOWS_DIR
    tf = wdir / THREAD_FILE
    if tf.is_file():
        return load_thread(tf), False
    names = sorted({p.stem for p in list(wdir.glob("*.yaml")) + list(wdir.glob("*.yml"))
                    if p.name not in (THREAD_FILE, "thread.yml")})
    if not names:
        return ThreadDef(thread=[]), True
    return ThreadDef(thread=[ThreadStage(mode="sequential",
                                         workflows=[ThreadWorkflow(name=n) for n in names])]), True


@dataclass
class ProjectPlan:
    root: Path
    thread: ThreadDef
    implicit: bool
    workflows: Dict[str, Any] = field(default_factory=dict)   # nom -> WorkflowDef (actifs + remplaçants)
    warnings: List[str] = field(default_factory=list)          # à signaler sans bloquer (ex. fallback)

    @property
    def active_names(self) -> List[str]:
        return [w.name for s in self.thread.thread for w in s.workflows if w.active]


def prepare_project(root: Path) -> ProjectPlan:
    """Charge et valide tout ce qu'il faut AVANT de lancer quoi que ce soit :
    thread.yaml, fichiers des workflows, manifestes des workflows actifs."""
    from hydra_etl.workflow.parser import load_workflow
    from hydra_etl.workflow.jobcheck import pipeline_errors

    root = Path(root).resolve()
    if not is_project_root(root):
        raise ProjectError([f"{root} is not a Hydra project (no .hydra/ folder)"])
    if not (root / WORKFLOWS_DIR).is_dir():
        raise ProjectError([f"{WORKFLOWS_DIR}/ folder not found in {root}"])
    try:
        thread, implicit = resolve_thread(root)
    except ValueError as e:
        raise ProjectError([f"{WORKFLOWS_DIR}/{THREAD_FILE}: {e}"]) from None

    errors: List[str] = []
    for name in missing_workflow_files(thread, root / WORKFLOWS_DIR):
        errors.append(f"{WORKFLOWS_DIR}/{THREAD_FILE}: workflow '{name}' has no file "
                      f"{WORKFLOWS_DIR}/{name}.yaml")
    plan = ProjectPlan(root=root, thread=thread, implicit=implicit)
    if errors:
        raise ProjectError(errors)

    def check_workflow(name: str) -> Optional[Any]:
        """Charge workflows/<name>.yaml et vérifie ses jobs ; erreurs dans `errors`."""
        path = workflow_file(root, name)
        try:
            wf = plan.workflows[name] = load_workflow(path)
        except Exception as e:  # noqa: BLE001 — message du parseur, déjà lisible
            errors.append(f"{WORKFLOWS_DIR}/{path.name}: {e}")
            return None
        for step in wf.steps:
            if step.type != "job" or not step.enabled or not step.job:
                continue
            jp = Path(step.job)
            if not jp.is_absolute():
                jp = path.parent / jp
            if not jp.resolve().is_dir():
                errors.append(f"{WORKFLOWS_DIR}/{path.name}: step '{step.name}' — "
                              f"job folder not found: {step.job}")
                continue
            # pipeline.from / to cassés : signalés avant tout lancement
            for problem in pipeline_errors(jp.resolve()):
                errors.append(f"{WORKFLOWS_DIR}/{path.name}: step '{step.name}' "
                              f"({step.job}) — {problem}")
        return wf

    for name in plan.active_names:
        check_workflow(name)

    # Fallbacks des workflows actifs : remplaçants présents et valides, noms
    # cités par la condition déclarés, même destinations (avertissement).
    for stage in thread.thread:
        for w in stage.workflows:
            if not w.active or not w.fallback:
                continue
            where = f"{WORKFLOWS_DIR}/{THREAD_FILE}: workflow '{w.name}' fallback"
            for alt in w.fallback.use:
                if not workflow_file(root, alt).is_file():
                    errors.append(f"{where}: '{alt}' has no file {WORKFLOWS_DIR}/{alt}.yaml")
                    continue
                if alt not in plan.workflows:
                    check_workflow(alt)
            errors.extend(f"{where}: {p}" for p in _condition_name_errors(root, plan, w))
            plan.warnings.extend(f"{where}: {m}" for m in _destination_warnings(root, plan, w))
    if errors:
        raise ProjectError(errors)
    return plan


def _workflow_jobs(root: Path, wf: Any) -> List[Path]:
    """Dossiers des jobs actifs d'un workflow chargé."""
    out = []
    for step in getattr(wf, "steps", []) or []:
        if step.type == "job" and step.enabled and step.job:
            jp = Path(step.job)
            if not jp.is_absolute():
                jp = Path(root) / WORKFLOWS_DIR / jp
            if jp.resolve().is_dir():
                out.append(jp.resolve())
    return out


def _yaml_section(path: Path, key: str) -> Dict[str, Any]:
    import yaml
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8-sig")) or {}
    except Exception:  # noqa: BLE001
        return {}
    sec = doc.get(key) if isinstance(doc, dict) else None
    return sec if isinstance(sec, dict) else {}


def _job_destinations(job_dir: Path) -> List[str]:
    """Destination réellement écrite par un job : « type:table »."""
    import yaml
    try:
        pipe = yaml.safe_load((job_dir / "pipeline.yaml").read_text(encoding="utf-8-sig")) or {}
    except Exception:  # noqa: BLE001
        return []
    p = pipe.get("pipeline") if isinstance(pipe, dict) else None
    if not isinstance(p, dict) and isinstance(pipe, dict) and isinstance(pipe.get("job"), dict):
        p = pipe["job"].get("pipeline")
    to = p.get("to") if isinstance(p, dict) else None
    d = _yaml_section(job_dir / "destinations.yaml", "destinations").get(to)
    if not isinstance(d, dict):
        return []
    load = d.get("load") if isinstance(d.get("load"), dict) else {}
    target = load.get("table") or load.get("file") or load.get("collection") or to
    return [f"{d.get('type', '?')}:{target}"]


def _destination_warnings(root: Path, plan: "ProjectPlan", w: ThreadWorkflow) -> List[str]:
    """Un remplaçant devrait écrire au même endroit que le workflow remplacé
    (même contrat). Différent = avertissement (ex. workflow de quarantaine)."""
    def dests(name: str) -> List[str]:
        wf = plan.workflows.get(name)
        return sorted({d for jd in _workflow_jobs(root, wf) for d in _job_destinations(jd)}) if wf else []
    base = dests(w.name)
    out = []
    for alt in w.fallback.use if w.fallback else []:
        if alt in plan.workflows and dests(alt) != base:
            out.append(f"'{alt}' writes to {dests(alt) or 'nothing'} instead of {base or 'nothing'} "
                       f"(fine for a quarantine workflow; otherwise check it)")
    return out


def _condition_name_errors(root: Path, plan: "ProjectPlan", w: ThreadWorkflow) -> List[str]:
    """Les sources / destinations citées par `when` doivent être déclarées dans
    un job du workflow (ou, à défaut, du projet)."""
    from hydra_etl.workflow.conditions import condition_sources
    if not (w.fallback and w.fallback.when):
        return []
    wf_jobs = _workflow_jobs(root, plan.workflows.get(w.name))
    all_jobs = [d for d in (Path(root) / "jobs").glob("*") if d.is_dir()]

    def declared(kind: str, jobs: List[Path]) -> set:
        return {k for jd in jobs for k in _yaml_section(jd / f"{kind}.yaml", kind)}

    out = []
    for fn, arg in condition_sources(w.fallback.when):
        if fn in ("source_available", "destination_available", "db.load"):
            kinds = {"source_available": ["sources"], "destination_available": ["destinations"],
                     "db.load": ["sources", "destinations"]}[fn]
            if not any(arg in declared(k, wf_jobs) or arg in declared(k, all_jobs) for k in kinds):
                what = " or ".join(f"{k}.yaml" for k in kinds)
                out.append(f"{fn}('{arg}'): '{arg}' is not declared in any job's {what}")
    return out


def _rows_written(run: Any) -> int:
    """Lignes écrites par les jobs d'un workflow exécuté (pour previous.rows)."""
    total = 0
    for st in getattr(getattr(run, "result", None), "steps", None) or []:
        jr = getattr(st, "job_result", None)
        total += int(getattr(jr, "rows_out", 0) or 0)
    return total


# Statuts d'un workflow dans un run de projet
SUCCESS, FAILED, INACTIVE, NOT_RUN = "success", "failed", "inactive", "not_run"


@dataclass
class WorkflowRun:
    name: str
    stage: int
    status: str
    duration: float = 0.0
    result: Any = None          # WorkflowResult
    error: Optional[str] = None
    iteration: int = 1          # passage dans une boucle (1 hors boucle)
    iterations: int = 1         # nombre total de passages prévus
    replaces: Optional[str] = None          # fallback : workflow du thread remplacé
    fallback_reason: Optional[str] = None   # pourquoi (condition, forcé, sonde en erreur)


@dataclass
class ProjectResult:
    project: str
    success: bool
    duration: float
    runs: List[WorkflowRun] = field(default_factory=list)

    @property
    def failed(self) -> List[WorkflowRun]:
        return [r for r in self.runs if r.status == FAILED]


# Événements envoyés au callback `on_event(kind, data)` :
#   "stage"     {"index", "total", "stage"}
#   "inactive"  WorkflowRun
#   "start"     {"name", "stage", "iteration", "iterations"}
#   "end"       WorkflowRun          (succès ou échec)
#   "not_run"   WorkflowRun
#   "delay"     {"seconds", "stage"}
#   "loop"      {"loop": ThreadLoop, "iteration": n, "iterations": N, "seconds": pause}
EventCallback = Callable[[str, Any], None]


class ProjectRunner:
    def __init__(self, plan: ProjectPlan, env: Optional[str] = None,
                 params: Optional[Dict[str, Any]] = None,
                 sleep: Callable[[float], None] = time.sleep,
                 force_fallback: Optional[List[str]] = None,
                 probe_timeout: Optional[float] = None) -> None:
        self.plan = plan
        self.env = env
        self.params = dict(params or {})
        self._sleep = sleep
        self._lock = threading.Lock()
        # --use-fallback : bascule forcée (répéter un scénario de secours)
        self.force_fallback = set(force_fallback or [])
        self.probe_timeout = probe_timeout
        self._wf_by_name = {w.name: w for st in plan.thread.thread for w in st.workflows}
        unknown = sorted(n for n in self.force_fallback
                         if not (self._wf_by_name.get(n) and self._wf_by_name[n].fallback))
        if unknown:
            raise ProjectError([f"--use-fallback {n}: workflow '{n}' has no fallback in "
                                f"{WORKFLOWS_DIR}/{THREAD_FILE}" for n in unknown])

    def _decide(self, name: str, previous: Any, stage: int, it: int, its: int,
                on_event: Optional[EventCallback]) -> "Tuple[str, Optional[str]]":
        """Juste avant le lancement : (workflow à lancer, raison du fallback ou None).
        Sondes de `fallback.when`, bascule forcée, politique on_probe_error."""
        w = self._wf_by_name.get(name)
        fb = w.fallback if w else None
        if fb is None:
            return name, None
        alt = next((a for a in fb.use if a in self.plan.workflows), None)
        if alt is None:                        # remplaçant non chargé (ne doit pas arriver)
            return name, None
        info = {"name": name, "use": alt, "stage": stage, "iteration": it, "iterations": its}
        if name in self.force_fallback:
            reason = "forced (--use-fallback)"
            self._emit(on_event, "fallback", {**info, "trigger": "forced", "reason": reason})
            return alt, reason
        if not fb.when:
            return name, None
        from hydra_etl.workflow.probes import ProbeContext, ProbeError, evaluate
        ctx = ProbeContext(root=self.plan.root, env=self.env, params=dict(self.params),
                           workflow_jobs=_workflow_jobs(self.plan.root, self.plan.workflows.get(name)),
                           previous=previous)
        if self.probe_timeout:
            ctx.timeout = self.probe_timeout
        try:
            ev = evaluate(fb.when, ctx)
        except ProbeError as e:
            if fb.on_probe_error == "replace":
                reason = f"check failed: {e}"
                self._emit(on_event, "fallback", {**info, "trigger": "probe_error", "reason": reason})
                return alt, reason
            self._emit(on_event, "probe_error", {**info, "error": str(e), "action": "keep"})
            return name, None
        if ev.value:
            self._emit(on_event, "fallback", {**info, "trigger": "when", "reason": ev.reason})
            return alt, ev.reason
        self._emit(on_event, "fallback_kept", {**info, "reason": ev.reason})
        return name, None

    def _emit(self, on_event: Optional[EventCallback], kind: str, data: Any) -> None:
        if on_event is None:
            return
        with self._lock:
            try:
                on_event(kind, data)
            except Exception:
                pass

    def _run_one(self, name: str, stage: int, on_event: Optional[EventCallback],
                 iteration: int = 1, iterations: int = 1,
                 replaces: Optional[str] = None, reason: Optional[str] = None) -> WorkflowRun:
        from hydra_etl.workflow.runner import WorkflowRunner

        self._emit(on_event, "start", {"name": name, "stage": stage,
                                       "iteration": iteration, "iterations": iterations,
                                       "replaces": replaces})
        wf = self.plan.workflows[name]
        path = workflow_file(self.plan.root, name)
        t0 = time.monotonic()
        try:
            result = WorkflowRunner(wf, base_dir=path.parent, env=self.env,
                                    project_root=self.plan.root,
                                    params=dict(self.params)).run()
            run = WorkflowRun(name=name, stage=stage,
                              status=SUCCESS if result.success else FAILED,
                              duration=time.monotonic() - t0, result=result,
                              error=None if result.success else result.error,
                              iteration=iteration, iterations=iterations)
        except Exception as e:  # noqa: BLE001
            run = WorkflowRun(name=name, stage=stage, status=FAILED,
                              duration=time.monotonic() - t0, error=f"{type(e).__name__}: {e}",
                              iteration=iteration, iterations=iterations)
        run.replaces, run.fallback_reason = replaces, reason
        self._emit(on_event, "end", run)
        return run

    def run(self, on_event: Optional[EventCallback] = None) -> ProjectResult:
        """Exécute les unités du thread (un workflow d'une étape séquentielle, ou
        une étape parallèle entière) avec un compteur de position : les boucles
        ramènent ce compteur en arrière, les délais d'étape s'appliquent en
        passant d'une étape à la suivante."""
        t0 = time.monotonic()
        th = self.plan.thread
        stages = th.thread
        units = th.units()
        active = {w.name: w.active for st in stages for w in st.workflows}
        # Boucles : unité de fin -> (boucle, unité de début, passages restants)
        loops = {}
        for lp in th.loops:
            loops[th.unit_of(lp.from_)] = [lp, th.unit_of(lp.to), lp.times - 1]
        # Passage courant d'une unité (1 hors boucle) et nombre total.
        def pass_of(ui: int):
            for end, (lp, start, remaining) in loops.items():
                if start <= ui <= end:
                    return lp.times - remaining, lp.times
            return 1, 1

        from hydra_etl.workflow.probes import Previous
        previous = Previous()                  # pour previous.status / previous.rows
        runs: List[WorkflowRun] = []
        stopped = False
        last_stage = -1
        pc = 0
        while pc < len(units):
            u = units[pc]
            stage_no = u.stage + 1
            it, its = pass_of(pc)
            if stopped:
                for n in u.names:
                    r = WorkflowRun(n, stage_no, INACTIVE if not active[n] else NOT_RUN)
                    runs.append(r)
                    self._emit(on_event, "inactive" if r.status == INACTIVE else "not_run", r)
                pc += 1
                continue
            if u.stage != last_stage:
                self._emit(on_event, "stage", {"index": stage_no, "total": len(stages),
                                               "stage": stages[u.stage]})
                last_stage = u.stage
            todo = [n for n in u.names if active[n]]
            for n in u.names:
                if not active[n]:
                    r = WorkflowRun(n, stage_no, INACTIVE, iteration=it, iterations=its)
                    runs.append(r)
                    self._emit(on_event, "inactive", r)
            # Fallback : décidé juste avant le lancement, workflow par workflow ;
            # le remplaçant prend la même place (étape, boucle, passage).
            plan_unit = [(n, *self._decide(n, previous, stage_no, it, its, on_event)) for n in todo]

            def launch(item):
                orig, actual, reason = item
                r = self._run_one(actual, stage_no, on_event, it, its, replaces=orig if reason else None,
                                  reason=reason)
                return r
            if u.parallel and len(plan_unit) > 1:
                with ThreadPoolExecutor(max_workers=len(plan_unit)) as pool:
                    done = list(pool.map(launch, plan_unit))
            else:
                done = [launch(x) for x in plan_unit]
            runs.extend(done)
            if done:
                from hydra_etl.workflow.probes import Previous
                previous = Previous(status=FAILED if any(r.status == FAILED for r in done) else SUCCESS,
                                    rows=sum(_rows_written(r) for r in done))
            elif u.names:
                from hydra_etl.workflow.probes import Previous
                previous = Previous(status=INACTIVE, rows=0)
            stopped = any(r.status == FAILED for r in done)
            if stopped:
                pc += 1
                continue
            # Boucle qui finit ici et a encore des passages : retour en arrière.
            lp_state = loops.get(pc)
            if lp_state and lp_state[2] > 0:
                lp, start, remaining = lp_state
                lp_state[2] = remaining - 1
                nxt, total = lp.times - lp_state[2], lp.times
                self._emit(on_event, "loop", {"loop": lp, "iteration": nxt, "iterations": total,
                                              "seconds": lp.delay_seconds})
                if lp.delay_seconds > 0:
                    self._sleep(lp.delay_seconds)
                pc = start
                last_stage = -1
                continue
            # Fin d'étape : délai avant l'étape suivante (jamais après la dernière).
            st = stages[u.stage]
            if u.last_in_stage and pc < len(units) - 1 and st.delay_seconds > 0:
                self._emit(on_event, "delay", {"seconds": st.delay_seconds, "stage": stage_no})
                self._sleep(st.delay_seconds)
            pc += 1
        return ProjectResult(project=self.plan.root.name,
                             success=not any(r.status == FAILED for r in runs),
                             duration=time.monotonic() - t0, runs=runs)


# ---------------------------------------------------------------------------
# Gestion des workflows d'un projet (hdrctl workflow add | remove | list)
# ---------------------------------------------------------------------------

def require_project(path: Optional[str] = None) -> Path:
    """Racine du projet désigné par `path` (ou contenant le dossier courant).
    ProjectError si aucun projet Hydra n'est trouvé."""
    start = Path(path) if path else Path.cwd()
    if path and not start.exists():
        raise ProjectError([f"{start} does not exist"])
    root = find_project_root(start)
    if root is None:
        raise ProjectError([f"{start.resolve()} is not inside a Hydra project (no .hydra/ folder)"])
    return root


def workflow_files(root: Path) -> Dict[str, Path]:
    """Nom → fichier, pour chaque workflows/*.yaml|yml (thread.yaml exclu)."""
    wdir = Path(root) / WORKFLOWS_DIR
    out: Dict[str, Path] = {}
    if not wdir.is_dir():
        return out
    for p in sorted(wdir.glob("*.yml")) + sorted(wdir.glob("*.yaml")):
        if p.name in (THREAD_FILE, "thread.yml"):
            continue
        out[p.stem] = p          # .yaml l'emporte sur .yml (lu après)
    return dict(sorted(out.items()))


def save_thread(root: Path, thread: ThreadDef) -> Path:
    from hydra_etl.workflow.thread import render_thread
    f = Path(root) / WORKFLOWS_DIR / THREAD_FILE
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(render_thread(thread), encoding="utf-8")
    return f


def _check_new_name(name: str) -> str:
    from hydra_etl.workflow.thread import ThreadWorkflow
    try:
        return ThreadWorkflow(name=name).name
    except Exception:
        raise ProjectError([f"invalid workflow name '{name}': use letters, digits, '-', '_' or '.', "
                            f"starting with a letter or a digit"]) from None


def new_workflow_yaml(name: str) -> str:
    return (
        'version: "1.0"\n'
        "workflow:\n"
        f"  name: {name}\n"
        '  description: ""\n'
        "  trigger:\n"
        "    type: manual\n"
        "  steps: []\n"
    )


def add_workflow(root: Path, name: Optional[str] = None,
                 fallback_for: Optional[str] = None) -> Tuple[str, Path, ThreadDef]:
    """Crée workflows/<name>.yaml (sans step) et l'inscrit en fin de thread.
    Sans nom : `workflow-<8 hex>`. Sans thread.yaml : il est créé avec les
    workflows existants (ordre alphabétique), puis le nouveau.

    `fallback_for` : le nouveau workflow devient un remplaçant de ce workflow
    du thread (ajouté à `fallback.use`, pas au thread). Sans fallback existant,
    il est créé avec `on_failure: true`. Un nom déjà cité comme remplaçant
    n'est jamais ajouté au thread."""
    import uuid
    from hydra_etl.workflow.thread import add_to_thread

    root = Path(root)
    existing = workflow_files(root)
    if name is None:
        name = f"workflow-{uuid.uuid4().hex[:8]}"
        while name in existing:
            name = f"workflow-{uuid.uuid4().hex[:8]}"
    name = _check_new_name(name)
    if name in existing:
        raise ProjectError([f"workflow '{name}' already exists: {existing[name]}"])
    try:
        thread, _ = resolve_thread(root)
    except ValueError as e:
        raise ProjectError([f"{WORKFLOWS_DIR}/{THREAD_FILE}: {e}"]) from None
    if fallback_for is not None:
        new_thread = _declare_fallback(thread, fallback_for, name)
    elif name in thread.workflow_names() or name in thread.fallback_names():
        # Déjà cité (dans le thread ou comme remplaçant) mais sans fichier :
        # on crée le fichier, le thread ne change pas.
        new_thread = thread
    else:
        new_thread = add_to_thread(thread, name)
    path = root / WORKFLOWS_DIR / f"{name}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_workflow_yaml(name), encoding="utf-8")
    save_thread(root, new_thread)
    return name, path, new_thread


def _declare_fallback(thread: ThreadDef, target: str, name: str) -> ThreadDef:
    """thread où `name` est ajouté aux remplaçants de `target`."""
    from hydra_etl.workflow.thread import ThreadFallback
    target = ThreadWorkflow(name=target).name
    if target not in thread.workflow_names():
        raise ProjectError([f"workflow '{target}' is not in {WORKFLOWS_DIR}/{THREAD_FILE}: "
                            f"a fallback is declared on a workflow of the thread"])
    stages = []
    for st in thread.thread:
        wfs = []
        for w in st.workflows:
            if w.name == target:
                fb = (w.fallback.model_copy(update={"use": [*w.fallback.use, name]})
                      if w.fallback else ThreadFallback(use=[name], on_failure=True))
                w = w.model_copy(update={"fallback": fb})
            wfs.append(w)
        stages.append(st.model_copy(update={"workflows": wfs}))
    try:
        return ThreadDef.model_validate({**thread.model_dump(by_alias=True),
                                         "thread": [s.model_dump() for s in stages]})
    except ValueError as e:
        raise ProjectError([f"{WORKFLOWS_DIR}/{THREAD_FILE}: {e}"]) from None


def _forget_in_studio(root: Path, path: Path) -> None:
    """Retire les traces Studio d'un fichier workflow supprimé : méta
    .hydra/workflows/<id>.json et entrée de .hydra/project.json."""
    import json
    rel = f"{WORKFLOWS_DIR}/{path.name}"
    meta_dir = root / PROJECT_MARKER / "workflows"
    ids = set()
    if meta_dir.is_dir():
        for f in meta_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            p = str(data.get("path") or "")
            if p and Path(p).name == path.name and Path(p).parent.name == WORKFLOWS_DIR:
                ids.add(data.get("id"))
                f.unlink()
    manifest = root / PROJECT_MARKER / "project.json"
    if manifest.is_file():
        try:
            m = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception:
            return
        before = m.get("workflows", [])
        after = [w for w in before if w.get("file") != rel and w.get("id") not in ids]
        if len(after) != len(before):
            m["workflows"] = after
            manifest.write_text(json.dumps(m, indent=2, ensure_ascii=False), encoding="utf-8")


def remove_workflow(root: Path, name: str) -> Tuple[Optional[Path], bool]:
    """Supprime workflows/<name>.yaml et son entrée du thread. Les jobs sont
    conservés. Retourne (fichier supprimé ou None, retiré du thread)."""
    from hydra_etl.workflow.thread import load_thread, remove_from_thread

    root = Path(root)
    name = name[:-5] if name.endswith(".yaml") else name[:-4] if name.endswith(".yml") else name
    files = workflow_files(root)
    tf = root / WORKFLOWS_DIR / THREAD_FILE
    thread = None
    if tf.is_file():
        try:
            thread = load_thread(tf)
        except ValueError as e:
            raise ProjectError([f"{WORKFLOWS_DIR}/{THREAD_FILE}: {e}"]) from None
    in_thread = thread is not None and name in thread.workflow_names()
    is_fallback = thread is not None and name in thread.fallback_names()
    if name not in files and not in_thread and not is_fallback:
        raise ProjectError([f"workflow '{name}' not found in {root / WORKFLOWS_DIR}"])
    removed: Optional[Path] = None
    if name in files:
        removed = files[name]
        removed.unlink()
        _forget_in_studio(root, removed)
    if in_thread or is_fallback:
        # retire aussi le nom des fallbacks qui le citaient
        save_thread(root, remove_from_thread(thread, name)[0])
    return removed, in_thread


@dataclass
class WorkflowInfo:
    name: str
    path: Optional[Path]
    stage: Optional[int] = None        # 1-based, None = absent du thread
    mode: Optional[str] = None
    active: Optional[bool] = None
    steps: Optional[int] = None        # None = manifeste illisible
    error: Optional[str] = None
    fallback_of: List[str] = field(default_factory=list)   # workflows du thread qu'il remplace


def list_workflows(root: Path) -> Tuple[List[WorkflowInfo], bool]:
    """Workflows du projet dans l'ordre du thread, puis ceux absents du thread.
    Retourne (liste, thread implicite)."""
    from hydra_etl.workflow.parser import load_workflow

    root = Path(root)
    files = workflow_files(root)
    thread, implicit = resolve_thread(root)
    out: List[WorkflowInfo] = []
    seen = set()
    for i, stage in enumerate(thread.thread, 1):
        for w in stage.workflows:
            seen.add(w.name)
            out.append(WorkflowInfo(w.name, files.get(w.name), i, stage.mode, w.active))
    for name, p in files.items():
        if name not in seen:
            out.append(WorkflowInfo(name, p))
    # remplaçants cités par un fallback (avec ou sans fichier)
    by_name = {i.name: i for i in out}
    for stage in thread.thread:
        for w in stage.workflows:
            for alt in (w.fallback.use if w.fallback else []):
                if alt not in by_name:
                    by_name[alt] = WorkflowInfo(alt, files.get(alt))
                    out.append(by_name[alt])
                by_name[alt].fallback_of.append(w.name)
    for info in out:
        if info.path is None:
            continue
        try:
            info.steps = len(load_workflow(info.path).steps)
        except Exception as e:  # noqa: BLE001
            info.error = str(e).splitlines()[0][:120]
    return out, implicit
