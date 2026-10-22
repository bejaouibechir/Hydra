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
    workflows: Dict[str, Any] = field(default_factory=dict)   # nom -> WorkflowDef (actifs)

    @property
    def active_names(self) -> List[str]:
        return [w.name for s in self.thread.thread for w in s.workflows if w.active]


def prepare_project(root: Path) -> ProjectPlan:
    """Charge et valide tout ce qu'il faut AVANT de lancer quoi que ce soit :
    thread.yaml, fichiers des workflows, manifestes des workflows actifs."""
    from hydra_etl.workflow.parser import load_workflow

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
    for name in plan.active_names:
        path = workflow_file(root, name)
        try:
            wf = plan.workflows[name] = load_workflow(path)
        except Exception as e:  # noqa: BLE001 — message du parseur, déjà lisible
            errors.append(f"{WORKFLOWS_DIR}/{path.name}: {e}")
            continue
        for step in wf.steps:
            if step.type != "job" or not step.enabled or not step.job:
                continue
            jp = Path(step.job)
            if not jp.is_absolute():
                jp = path.parent / jp
            if not jp.resolve().is_dir():
                errors.append(f"{WORKFLOWS_DIR}/{path.name}: step '{step.name}' — "
                              f"job folder not found: {step.job}")
    if errors:
        raise ProjectError(errors)
    return plan


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
#   "start"     {"name", "stage"}
#   "end"       WorkflowRun          (succès ou échec)
#   "not_run"   WorkflowRun
#   "delay"     {"seconds", "stage"}
EventCallback = Callable[[str, Any], None]


class ProjectRunner:
    def __init__(self, plan: ProjectPlan, env: Optional[str] = None,
                 params: Optional[Dict[str, Any]] = None,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.plan = plan
        self.env = env
        self.params = dict(params or {})
        self._sleep = sleep
        self._lock = threading.Lock()

    def _emit(self, on_event: Optional[EventCallback], kind: str, data: Any) -> None:
        if on_event is None:
            return
        with self._lock:
            try:
                on_event(kind, data)
            except Exception:
                pass

    def _run_one(self, name: str, stage: int, on_event: Optional[EventCallback]) -> WorkflowRun:
        from hydra_etl.workflow.runner import WorkflowRunner

        self._emit(on_event, "start", {"name": name, "stage": stage})
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
                              error=None if result.success else result.error)
        except Exception as e:  # noqa: BLE001
            run = WorkflowRun(name=name, stage=stage, status=FAILED,
                              duration=time.monotonic() - t0, error=f"{type(e).__name__}: {e}")
        self._emit(on_event, "end", run)
        return run

    def run(self, on_event: Optional[EventCallback] = None) -> ProjectResult:
        t0 = time.monotonic()
        runs: List[WorkflowRun] = []
        stages = self.plan.thread.thread
        stopped = False
        for i, stage in enumerate(stages, 1):
            if stopped:
                for w in stage.workflows:
                    r = WorkflowRun(w.name, i, INACTIVE if not w.active else NOT_RUN)
                    runs.append(r)
                    self._emit(on_event, "inactive" if r.status == INACTIVE else "not_run", r)
                continue
            self._emit(on_event, "stage", {"index": i, "total": len(stages), "stage": stage})
            active = [w.name for w in stage.workflows if w.active]
            if stage.mode == "parallel" and len(active) > 1:
                for w in stage.workflows:
                    if not w.active:
                        r = WorkflowRun(w.name, i, INACTIVE)
                        runs.append(r)
                        self._emit(on_event, "inactive", r)
                with ThreadPoolExecutor(max_workers=len(active)) as pool:
                    stage_runs = list(pool.map(lambda n: self._run_one(n, i, on_event), active))
                runs.extend(stage_runs)
                stopped = any(r.status == FAILED for r in stage_runs)
            else:
                # Ordre du fichier, inactifs compris.
                for w in stage.workflows:
                    if not w.active:
                        r = WorkflowRun(w.name, i, INACTIVE)
                        self._emit(on_event, "inactive", r)
                    elif stopped:
                        r = WorkflowRun(w.name, i, NOT_RUN)
                        self._emit(on_event, "not_run", r)
                    else:
                        r = self._run_one(w.name, i, on_event)
                        stopped = r.status == FAILED
                    runs.append(r)
            if not stopped and i < len(stages) and stage.delay_seconds > 0:
                self._emit(on_event, "delay", {"seconds": stage.delay_seconds, "stage": i})
                self._sleep(stage.delay_seconds)
        return ProjectResult(project=self.plan.root.name,
                             success=not any(r.status == FAILED for r in runs),
                             duration=time.monotonic() - t0, runs=runs)
