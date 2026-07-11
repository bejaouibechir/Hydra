"""api/routers/environments.py — Gestion des environnements (.env files)."""
from typing import List
from fastapi import APIRouter, HTTPException, Query

from api import store
from api.models import EnvironmentCreate, EnvironmentResponse, EnvironmentUpdate, MessageResponse

router = APIRouter()


@router.get("", response_model=List[EnvironmentResponse])
def list_environments(project_id: str = Query(...)):
    if not store.get_project(project_id):
        raise HTTPException(404, detail=f"Project '{project_id}' not found")
    return store.list_environments(project_id)


@router.post("", response_model=EnvironmentResponse, status_code=201)
def create_environment(body: EnvironmentCreate):
    if not store.get_project(body.project_id):
        raise HTTPException(404, detail=f"Project '{body.project_id}' not found")
    return store.create_environment(body.project_id, body.name, body.vars)


@router.get("/{env_name}", response_model=EnvironmentResponse)
def get_environment(env_name: str, project_id: str = Query(...)):
    env = store.get_environment(project_id, env_name)
    if not env:
        raise HTTPException(404, detail=f"Environment '{env_name}' not found")
    return env


@router.put("/{env_name}", response_model=EnvironmentResponse)
def update_environment(env_name: str, body: EnvironmentUpdate, project_id: str = Query(...)):
    env = store.update_environment(project_id, env_name, body.vars or {})
    if not env:
        raise HTTPException(404, detail=f"Environment '{env_name}' not found")
    return env


@router.delete("/{env_name}", response_model=MessageResponse)
def delete_environment(env_name: str, project_id: str = Query(...)):
    if not store.delete_environment(project_id, env_name):
        raise HTTPException(404, detail=f"Environment '{env_name}' not found")
    return {"message": f"Environment '{env_name}' deleted"}
