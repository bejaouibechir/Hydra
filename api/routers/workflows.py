"""api/routers/workflows.py — CRUD workflows + publish/activate."""
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query

from api import store
from api.models import MessageResponse, WorkflowCreate, WorkflowResponse, WorkflowUpdate

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
    return store.create_workflow(
        project_id=body.project_id,
        name=body.name,
        description=body.description,
        trigger_type=body.trigger_type,
        cron=body.cron,
    )


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
    return wf


@router.post("/{workflow_id}/publish", response_model=WorkflowResponse)
def publish_workflow(workflow_id: str, project_id: str = Query(...)):
    """Publie un workflow (passe draft → published)."""
    wf = store.publish_workflow(project_id, workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found")
    return wf


@router.delete("/{workflow_id}", response_model=MessageResponse)
def delete_workflow(workflow_id: str, project_id: str = Query(...)):
    if not store.delete_workflow(project_id, workflow_id):
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found")
    return {"message": f"Workflow '{workflow_id}' deleted"}
