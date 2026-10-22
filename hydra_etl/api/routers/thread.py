"""api/routers/thread.py — Ordre d'exécution des workflows d'un projet
(workflows/thread.yaml), comme `hdrctl run <projet>`.

  GET  /api/projects/{id}/thread   thread + workflows du projet
  PUT  /api/projects/{id}/thread   enregistre thread.yaml (validé)
  POST /api/projects/{id}/check    vérifie le projet comme `hdrctl run --dry-run`

Le lancement passe par POST /api/runs avec workflow_path = dossier du projet.
"""
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from hydra_etl.api import store
from hydra_etl.workflow.project import (
    ProjectError, prepare_project, resolve_thread, save_thread, workflow_files,
)
from hydra_etl.workflow.thread import missing_workflow_files, parse_thread

router = APIRouter()


class ThreadResponse(BaseModel):
    thread: Dict[str, Any]            # {"version": "1.0", "thread": [stages…]}
    implicit: bool                    # pas de thread.yaml : ordre alphabétique
    workflows: List[str]              # workflows/*.yaml du projet
    missing: List[str]                # noms du thread sans fichier


class ThreadPayload(BaseModel):
    thread: List[Dict[str, Any]]


class CheckResponse(BaseModel):
    ok: bool
    errors: List[str]
    active: List[str]                 # workflows qui seraient lancés, dans l'ordre


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
        thread=th.model_dump(), implicit=implicit,
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
        th = parse_thread({"version": "1.0", "thread": body.thread})
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
    return CheckResponse(ok=True, errors=[], active=plan.active_names)
