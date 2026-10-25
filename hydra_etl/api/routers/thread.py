"""api/routers/thread.py — Ordre d'exécution des workflows d'un projet
(workflows/thread.yaml), comme `hdrctl run <projet>`.

  GET  /api/projects/{id}/thread   thread + workflows du projet
  PUT  /api/projects/{id}/thread   enregistre thread.yaml (validé)
  POST /api/projects/{id}/check    vérifie le projet comme `hdrctl run --dry-run`
  GET  /api/projects/{id}/conditions        aide à l'écriture de `fallback.when`
  POST /api/projects/{id}/conditions/check  vérifie une condition (syntaxe, noms)

Le lancement passe par POST /api/runs avec workflow_path = dossier du projet.
"""
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from hydra_etl.api import store
from hydra_etl.workflow.conditions import (
    ATTRIBUTE_HELP, FUNCTION_HELP, FUNCTIONS, ConditionError, parse_condition,
)
from hydra_etl.workflow.project import (
    ProjectError, condition_name_errors, declared_names, prepare_project, project_job_dirs,
    resolve_thread, save_thread, workflow_files,
)
from hydra_etl.workflow.thread import missing_workflow_files, parse_thread

router = APIRouter()


class ThreadResponse(BaseModel):
    thread: Dict[str, Any]            # {"version": "1.0", "thread": [stages…], "loops": [...]}
    implicit: bool                    # pas de thread.yaml : ordre alphabétique
    workflows: List[str]              # workflows/*.yaml du projet
    missing: List[str]                # noms du thread sans fichier


class ThreadPayload(BaseModel):
    thread: List[Dict[str, Any]]
    loops: List[Dict[str, Any]] = []      # [{"from", "to", "times", "delay"}]


class CheckResponse(BaseModel):
    ok: bool
    errors: List[str]
    active: List[str]                 # workflows qui seraient lancés, dans l'ordre
    warnings: List[str] = []          # à signaler sans bloquer (ex. fallback)


def _root(project_id: str) -> Path:
    if not store.get_project(project_id):
        raise HTTPException(404, detail=f"Project '{project_id}' not found")
    return store._resolve_project_path(project_id)


def _describe(root: Path) -> ThreadResponse:
    try:
        th, implicit = resolve_thread(root)
    except ValueError as e:
        raise HTTPException(422, detail=f"workflows/thread.yaml: {e}")
    return ThreadResponse(
        thread=th.model_dump(by_alias=True), implicit=implicit,
        workflows=sorted(workflow_files(root)),
        missing=missing_workflow_files(th, root / "workflows"),
    )


@router.get("/{project_id}/thread", response_model=ThreadResponse)
def get_thread(project_id: str):
    return _describe(_root(project_id))


@router.put("/{project_id}/thread", response_model=ThreadResponse)
def put_thread(project_id: str, body: ThreadPayload):
    root = _root(project_id)
    try:
        th = parse_thread({"version": "1.0", "thread": body.thread, "loops": body.loops})
    except ValueError as e:
        raise HTTPException(422, detail=str(e))
    missing = missing_workflow_files(th, root / "workflows")
    if missing:
        raise HTTPException(422, detail=f"no workflow file for: {', '.join(missing)}")
    save_thread(root, th)
    return _describe(root)


@router.post("/{project_id}/check", response_model=CheckResponse)
def check_project(project_id: str):
    root = _root(project_id)
    try:
        plan = prepare_project(root)
    except ProjectError as e:
        return CheckResponse(ok=False, errors=e.errors, active=[])
    return CheckResponse(ok=True, errors=[], active=plan.active_names, warnings=plan.warnings)


class ConditionFunction(BaseModel):
    name: str
    arg: str                          # source | destination | path | url | secret | database
    returns: str                      # bool | bytes | seconds | number
    help: str


class ConditionHelp(BaseModel):
    functions: List[ConditionFunction]
    attributes: Dict[str, str]        # previous.status, previous.rows → description
    sources: List[str]                # déclarées dans les jobs du projet
    destinations: List[str]
    secrets: List[str]                # noms seulement, jamais les valeurs


class ConditionPayload(BaseModel):
    when: str


class ConditionCheck(BaseModel):
    ok: bool
    error: Optional[str] = None


@router.get("/{project_id}/conditions", response_model=ConditionHelp)
def condition_help(project_id: str):
    from hydra_etl.internal.config.secrets import project_secrets
    root = _root(project_id)
    jobs = project_job_dirs(root)
    try:
        secrets = sorted(project_secrets(root))
    except Exception:  # noqa: BLE001 — fichier de secrets illisible : pas d'aide
        secrets = []
    return ConditionHelp(
        functions=[ConditionFunction(name=n, arg=FUNCTION_HELP[n][0], returns=FUNCTIONS[n][1],
                                     help=FUNCTION_HELP[n][1]) for n in FUNCTIONS],
        attributes=ATTRIBUTE_HELP,
        sources=declared_names(jobs, "sources"),
        destinations=declared_names(jobs, "destinations"),
        secrets=secrets,
    )


@router.post("/{project_id}/conditions/check", response_model=ConditionCheck)
def condition_check(project_id: str, body: ConditionPayload):
    root = _root(project_id)
    try:
        parse_condition(body.when)
    except ConditionError as e:
        return ConditionCheck(ok=False, error=str(e))
    jobs = project_job_dirs(root)
    problems = condition_name_errors(body.when, jobs, jobs)
    return ConditionCheck(ok=not problems, error="; ".join(problems) or None)
