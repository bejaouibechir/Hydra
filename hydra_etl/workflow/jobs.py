"""
workflow/jobs.py — Les jobs d'un projet et leur place dans les workflows
(`hdrctl job add | attach | detach`).

Un job est un dossier `jobs/<nom>/` (sources, destinations, pipeline,
transformations). Un workflow l'utilise par un step `type: job`.

Ordre dans un workflow = chaîne séquentielle (décision du 22/10/2026) :
- attacher en fin : le nouveau step dépend du dernier step ;
- attacher en position N : il dépend du step N-1, et le step qui occupait la
  position N dépend désormais de lui ;
- détacher : les steps qui dépendaient du job héritent de ses dépendances, la
  chaîne reste continue.

Le fichier du workflow est réécrit : ses commentaires ne sont pas conservés.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from hydra_etl.workflow.project import ProjectError, WORKFLOWS_DIR, workflow_files

JOBS_DIR = "jobs"


def job_path(root: Path, name: str) -> Path:
    return Path(root) / JOBS_DIR / name


def check_job_name(name: str) -> str:
    from hydra_etl.workflow.thread import _NAME_RE
    n = (name or "").strip()
    if not _NAME_RE.match(n):
        raise ProjectError([f"invalid job name '{name}': use letters, digits, '-', '_' or '.', "
                            f"starting with a letter or a digit"])
    return n


def create_job(root: Path, name: str, template: str = "csv") -> Tuple[Path, List[str]]:
    """Crée jobs/<name>/ depuis un template de `hdrctl init`."""
    from hydra_etl.cli.hdrctl import create_job_structure  # templates partagés avec init

    name = check_job_name(name)
    target = job_path(root, name)
    if target.exists():
        raise ProjectError([f"job '{name}' already exists: {target}"])
    created = create_job_structure(target, template, False)
    return target, created


# ---------------------------------------------------------------------------
# Lecture / écriture d'un workflow
# ---------------------------------------------------------------------------

class _Dumper(yaml.SafeDumper):
    """Listes de scalaires en flow (`depends_on: [a, b]`), séquences indentées."""

    def increase_indent(self, flow: bool = False, indentless: bool = False):
        return super().increase_indent(flow, False)


def _repr_list(dumper: yaml.SafeDumper, data: list):
    flow = all(not isinstance(x, (dict, list)) for x in data)
    return dumper.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=flow)


def _repr_str(dumper: yaml.SafeDumper, data: str):
    # Une chaîne qui serait relue comme un autre type ("1.0", "true", "") est
    # écrite entre guillemets doubles, comme dans les fichiers de hdrctl init.
    style = None
    if "\n" in data:
        style = "|"
    else:
        try:
            if not isinstance(yaml.safe_load(data), str):
                style = '"'
        except yaml.YAMLError:
            style = '"'
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_Dumper.add_representer(list, _repr_list)
_Dumper.add_representer(str, _repr_str)


def dump_workflow(doc: Dict[str, Any]) -> str:
    return yaml.dump(doc, Dumper=_Dumper, sort_keys=False, allow_unicode=True,
                     default_flow_style=False, width=100)


def _workflow_file(root: Path, workflow: str) -> Path:
    name = workflow[:-5] if workflow.endswith(".yaml") else workflow[:-4] if workflow.endswith(".yml") else workflow
    f = workflow_files(root).get(name)
    if f is None:
        raise ProjectError([f"workflow '{name}' not found in {Path(root) / WORKFLOWS_DIR} "
                            f"(create it with: hdrctl workflow add {name})"])
    return f


def _load_doc(path: Path) -> Dict[str, Any]:
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    except yaml.YAMLError as e:
        raise ProjectError([f"{path.name}: invalid YAML: {e}"]) from None
    if not isinstance(doc, dict) or not isinstance(doc.get("workflow"), dict):
        raise ProjectError([f"{path.name}: expected a top-level 'workflow' mapping"])
    wf = doc["workflow"]
    if wf.get("steps") is None:
        wf["steps"] = []
    if not isinstance(wf["steps"], list):
        raise ProjectError([f"{path.name}: 'workflow.steps' must be a list"])
    return doc


def _save_doc(path: Path, doc: Dict[str, Any]) -> None:
    """Valide le workflow modifié avant d'écrire : un fichier invalide n'est
    jamais produit."""
    from hydra_etl.workflow.models import WorkflowDef
    try:
        WorkflowDef.model_validate(doc["workflow"])
    except Exception as e:  # noqa: BLE001
        raise ProjectError([f"{path.name}: the change would make the workflow invalid: {e}"]) from None
    path.write_text(dump_workflow(doc), encoding="utf-8")


def _deps(step: Dict[str, Any]) -> List[str]:
    d = step.get("depends_on") or []
    return [d] if isinstance(d, str) else list(d)


def _points_to(step: Dict[str, Any], wf_dir: Path, target: Path) -> bool:
    if step.get("type") != "job" or not step.get("job"):
        return False
    p = Path(str(step["job"]))
    if not p.is_absolute():
        p = wf_dir / p
    return p.resolve() == target.resolve()


def job_usage(root: Path, job: str) -> Dict[str, List[str]]:
    """Workflow → noms des steps qui utilisent jobs/<job>."""
    target = job_path(root, job)
    out: Dict[str, List[str]] = {}
    for name, f in workflow_files(root).items():
        try:
            doc = _load_doc(f)
        except ProjectError:
            continue
        steps = [s.get("name") for s in doc["workflow"]["steps"]
                 if isinstance(s, dict) and _points_to(s, f.parent, target)]
        if steps:
            out[name] = steps
    return out


# ---------------------------------------------------------------------------
# attach / detach
# ---------------------------------------------------------------------------

@dataclass
class AttachResult:
    workflow: str
    step: str
    position: int                     # 1-based
    after: Optional[str]              # step dont il dépend (None : premier)
    rewired: Optional[str] = None     # step suivant recâblé sur le nouveau
    not_rewired: Optional[str] = None # step suivant laissé tel quel (graphe non linéaire)


def attach_job(root: Path, job: str, workflow: str, position: Optional[int] = None) -> AttachResult:
    root = Path(root)
    job = check_job_name(job)
    target = job_path(root, job)
    if not target.is_dir():
        raise ProjectError([f"job '{job}' not found: {target} (create it with: hdrctl job add {job})"])
    wf_file = _workflow_file(root, workflow)
    doc = _load_doc(wf_file)
    steps: List[Dict[str, Any]] = doc["workflow"]["steps"]
    if any(isinstance(s, dict) and _points_to(s, wf_file.parent, target) for s in steps):
        raise ProjectError([f"job '{job}' is already attached to workflow '{wf_file.stem}'"])
    n = len(steps)
    if position is None:
        position = n + 1
    if not 1 <= position <= n + 1:
        raise ProjectError([f"position {position} is out of range: workflow '{wf_file.stem}' has "
                            f"{n} step(s), use 1 to {n + 1}"])
    names = {s.get("name") for s in steps if isinstance(s, dict)}
    step_name, k = job, 2
    while step_name in names:
        step_name, k = f"{job}-{k}", k + 1

    i = position - 1
    prev = steps[i - 1] if i > 0 else None
    nxt = steps[i] if i < n else None
    rel = os.path.relpath(target, wf_file.parent).replace(os.sep, "/")
    new = {"name": step_name, "type": "job", "job": rel,
           "depends_on": [prev["name"]] if prev else [], "on_failure": "fail"}
    res = AttachResult(workflow=wf_file.stem, step=step_name, position=position,
                       after=prev["name"] if prev else None)
    if nxt is not None:
        deps = _deps(nxt)
        if prev is not None and prev["name"] in deps:
            nxt["depends_on"] = [step_name if d == prev["name"] else d for d in deps]
            res.rewired = nxt.get("name")
        elif prev is None and not deps:
            nxt["depends_on"] = [step_name]
            res.rewired = nxt.get("name")
        else:
            res.not_rewired = nxt.get("name")
    steps.insert(i, new)
    _save_doc(wf_file, doc)
    return res


@dataclass
class DetachResult:
    workflow: str
    steps: List[str]
    rewired: Dict[str, List[str]] = field(default_factory=dict)   # step → nouvelles dépendances


def detach_job(root: Path, job: str, workflow: Optional[str] = None) -> List[DetachResult]:
    """Retire le job d'un workflow (ou de tous). Liste vide : le job n'était
    attaché nulle part (ou pas à ce workflow : voir job_usage)."""
    root = Path(root)
    target = job_path(root, job)
    files = [ _workflow_file(root, workflow) ] if workflow else list(workflow_files(root).values())
    results: List[DetachResult] = []
    for wf_file in files:
        try:
            doc = _load_doc(wf_file)
        except ProjectError:
            if workflow:
                raise
            continue
        steps = doc["workflow"]["steps"]
        removed = [s for s in steps if isinstance(s, dict) and _points_to(s, wf_file.parent, target)]
        if not removed:
            continue
        res = DetachResult(workflow=wf_file.stem, steps=[s["name"] for s in removed])
        for r in removed:
            steps.remove(r)
            r_deps = _deps(r)
            for s in steps:
                deps = _deps(s)
                if r["name"] in deps:
                    new: List[str] = []
                    for d in deps:
                        for x in (r_deps if d == r["name"] else [d]):
                            if x not in new and x != s.get("name"):
                                new.append(x)
                    s["depends_on"] = new
                    res.rewired[s["name"]] = new
        _save_doc(wf_file, doc)
        results.append(res)
    return results


# ---------------------------------------------------------------------------
# Vue d'ensemble (hdrctl job list, hdrctl list <projet>)
# ---------------------------------------------------------------------------

REQUIRED_JOB_FILES = ("sources.yaml", "destinations.yaml", "pipeline.yaml")


@dataclass
class JobInfo:
    name: str                                   # nom du dossier, ou chemin relatif hors jobs/
    path: Path
    exists: bool
    missing: List[str] = field(default_factory=list)            # fichiers requis absents
    used_by: List[Tuple[str, str]] = field(default_factory=list)  # (workflow, step)


def jobs_overview(root: Path) -> List[JobInfo]:
    """Jobs du projet (dossiers jobs/*) avec les workflows qui les utilisent,
    puis les dossiers référencés par un workflow mais absents."""
    root = Path(root).resolve()
    infos: Dict[Path, JobInfo] = {}
    jdir = root / JOBS_DIR
    if jdir.is_dir():
        for d in sorted(p for p in jdir.iterdir() if p.is_dir() and not p.name.startswith(".")):
            r = d.resolve()
            infos[r] = JobInfo(d.name, r, True,
                               [f for f in REQUIRED_JOB_FILES if not (d / f).is_file()
                                and not (d / f.replace(".yaml", ".yml")).is_file()])
    for wf_name, f in workflow_files(root).items():
        try:
            steps = _load_doc(f)["workflow"]["steps"]
        except ProjectError:
            continue
        for s in steps:
            if not isinstance(s, dict) or s.get("type") != "job" or not s.get("job"):
                continue
            p = Path(str(s["job"]))
            r = (p if p.is_absolute() else f.parent / p).resolve()
            if r not in infos:
                try:
                    label = r.relative_to(jdir.resolve()).as_posix()
                except ValueError:
                    label = os.path.relpath(r, root).replace(os.sep, "/")
                infos[r] = JobInfo(label, r, r.is_dir())
            infos[r].used_by.append((wf_name, str(s.get("name"))))
    return list(infos.values())
