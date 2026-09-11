"""api/routers/workflows.py — CRUD workflows + publish/activate + trigger webhook."""
import uuid
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from hydra_etl.api import store, scheduler
from hydra_etl.api.models import MessageResponse, RunResponse, WorkflowCreate, WorkflowResponse, WorkflowUpdate

router = APIRouter()


@router.get("", response_model=List[WorkflowResponse])
def list_workflows(project_id: Optional[str] = Query(None)):
    """Liste les workflows, filtrable par project_id."""
    if project_id:
        proj = store.get_project(project_id)
        if not proj:
            raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
        return store.list_workflows(project_id)
    # Tous les workflows de tous les projets
    all_wf = []
    for p in store.list_projects():
        all_wf.extend(store.list_workflows(p.id))
    return all_wf


@router.post("", response_model=WorkflowResponse, status_code=201)
def create_workflow(body: WorkflowCreate):
    if not store.get_project(body.project_id):
        raise HTTPException(status_code=404, detail=f"Project '{body.project_id}' not found")
    wf = store.create_workflow(
        project_id=body.project_id,
        name=body.name,
        description=body.description,
        trigger_type=body.trigger_type,
        cron=body.cron,
    )
    scheduler.sync_workflow(body.project_id, wf.id)
    return wf


@router.get("/scheduled/list")
def list_scheduled_workflows():
    """Liste des workflows actuellement planifiés (jobs cron actifs)."""
    return scheduler.list_scheduled()


@router.get("/{workflow_id}", response_model=WorkflowResponse)
def get_workflow(workflow_id: str, project_id: str = Query(...)):
    wf = store.get_workflow(project_id, workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found")
    return wf


@router.put("/{workflow_id}", response_model=WorkflowResponse)
def update_workflow(workflow_id: str, body: WorkflowUpdate, project_id: str = Query(...)):
    wf = store.update_workflow(project_id, workflow_id, body.model_dump(exclude_none=True))
    if not wf:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found")
    scheduler.sync_workflow(project_id, workflow_id)
    return wf


@router.post("/{workflow_id}/publish", response_model=WorkflowResponse)
def publish_workflow(workflow_id: str, project_id: str = Query(...)):
    """Publie un workflow (passe draft → published)."""
    wf = store.publish_workflow(project_id, workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found")
    scheduler.sync_workflow(project_id, workflow_id)
    return wf


@router.post("/{workflow_id}/trigger", response_model=RunResponse, status_code=202)
def trigger_workflow(workflow_id: str, project_id: str = Query(...)):
    """Déclenche un workflow dont trigger.type == 'webhook' (POST externe).

    Réutilise le chemin d'exécution des runs manuels. En v1 (mono-user local),
    aucun token n'est exigé ; l'endpoint refuse simplement les workflows dont le
    trigger n'est pas 'webhook' pour éviter les déclenchements involontaires.
    """
    wf = store.get_workflow(project_id, workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found")
    # Source de vérité = le YAML (comme le runner/scheduler) ; repli sur la métadonnée.
    yaml_trig, _ = scheduler._trigger_from_file(wf.path)
    effective_trig = yaml_trig or wf.trigger_type or "manual"
    if effective_trig != "webhook":
        raise HTTPException(
            status_code=409,
            detail=f"Workflow '{wf.name}' trigger is '{effective_trig}', not 'webhook'",
        )
    if not wf.path or not Path(wf.path).exists():
        raise HTTPException(status_code=404, detail=f"Workflow file not found: {wf.path}")

    from hydra_etl.api.routers.runs import _execute_workflow
    import threading

    run_id = str(uuid.uuid4())[:8]
    run = RunResponse(
        run_id=run_id,
        workflow_name=wf.name,
        workflow_path=str(Path(wf.path).resolve()),
        status="pending",
        started_at=datetime.now(timezone.utc).isoformat(),
        trigger="webhook",
    )
    store.save_run(run)
    # Exécution en tâche de fond (thread) — l'appelant récupère le run "pending".
    threading.Thread(
        target=_execute_workflow, args=(run_id, str(wf.path), None, None), daemon=True,
    ).start()
    return run


@router.delete("/{workflow_id}", response_model=MessageResponse)
def delete_workflow(workflow_id: str, project_id: str = Query(...)):
    if not store.delete_workflow(project_id, workflow_id):
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found")
    scheduler.remove_workflow(workflow_id)
    return {"message": f"Workflow '{workflow_id}' deleted"}
