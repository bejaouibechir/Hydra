"""api/routers/global_env.py — Environnements et variables globales (Studio :
Global settings › Environments, sélecteur d'environnement actif).

Variables globales : ~/.hydra/env (communes) et ~/.hydra/env.<env>, partagées
par tous les projets de la machine où tourne l'API. Ce ne sont pas des secrets :
les valeurs sont renvoyées telles quelles (les secrets restent dans .hydra/secrets*).
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from hydra_etl.api import store
from hydra_etl.internal.config import env_admin as ea
from hydra_etl.internal.config.loader import global_env_file, hydra_home

router = APIRouter()


class GlobalEnv(BaseModel):
    name: str
    vars: Dict[str, str] = {}
    file: str


class GlobalEnvResponse(BaseModel):
    home: str
    common: GlobalEnv
    environments: List[GlobalEnv]


class EnvName(BaseModel):
    name: str
    global_vars: int = 0
    params: int = 0
    secrets: int = 0
    in_global: bool = False
    in_project: bool = False


class CreateBody(BaseModel):
    name: str
    project_id: Optional[str] = None


class RenameBody(BaseModel):
    new_name: str
    project_id: Optional[str] = None


class VarsBody(BaseModel):
    env: Optional[str] = None          # None : variables communes
    vars: Dict[str, str] = {}


def _root(project_id: Optional[str]) -> Optional[Path]:
    if not project_id:
        return None
    if not store.get_project(project_id):
        raise HTTPException(404, detail=f"Project '{project_id}' not found")
    return store._resolve_project_path(project_id)


def _call(fn, *a, **k):
    try:
        return fn(*a, **k)
    except (ea.EnvAdminError, ValueError) as e:
        raise HTTPException(422, detail=str(e))


def _describe() -> GlobalEnvResponse:
    from hydra_etl.internal.config.loader import global_env_names
    envs = [GlobalEnv(name=n, vars=ea.global_vars(n), file=str(global_env_file(n)))
            for n in global_env_names()]
    return GlobalEnvResponse(
        home=str(hydra_home()),
        common=GlobalEnv(name="", vars=ea.global_vars(None), file=str(global_env_file(None))),
        environments=envs,
    )


@router.get("", response_model=GlobalEnvResponse)
def get_global_env():
    return _describe()


@router.get("/names", response_model=List[EnvName])
def env_names(project_id: Optional[str] = None):
    """Environnements connus : globaux + ceux du projet (sélecteurs Studio)."""
    root = _root(project_id)
    return [EnvName(name=i.name, global_vars=i.global_vars, params=i.params, secrets=i.secrets,
                    in_global=i.global_file, in_project=i.project_file)
            for i in _call(ea.list_environments, root)]


@router.post("/environments", response_model=GlobalEnvResponse, status_code=201)
def create_env(body: CreateBody):
    _call(ea.create_environment, body.name, _root(body.project_id), global_only=not body.project_id)
    return _describe()


@router.put("/environments/{name}", response_model=GlobalEnvResponse)
def rename_env(name: str, body: RenameBody):
    _call(ea.rename_environment, name, body.new_name, _root(body.project_id))
    return _describe()


@router.delete("/environments/{name}", response_model=GlobalEnvResponse)
def delete_env(name: str, project_id: Optional[str] = None):
    _call(ea.delete_environment, name, _root(project_id))
    return _describe()


@router.put("/vars", response_model=GlobalEnvResponse)
def put_vars(body: VarsBody):
    _call(ea.replace_global_vars, body.env or None, body.vars)
    return _describe()
