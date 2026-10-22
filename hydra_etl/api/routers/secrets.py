"""api/routers/secrets.py — Secrets du projet (Studio : onglet Secrets).

Fichier : <projet>/.hydra/secrets (name=value, ignoré par git), ou celui que
désigne HYDRA_SECRETS_FILE. L'API ne renvoie JAMAIS les valeurs : seulement les
noms, et la variable d'environnement qui l'emporte quand il y en a une.
"""
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from hydra_etl.api import store
from hydra_etl.internal.config.secrets import (
    SECRETS_FILE_ENV, SecretResolutionError, delete_secret, env_override,
    load_secrets_file, secrets_file_for, set_secret,
)

router = APIRouter()


class SecretInfo(BaseModel):
    name: str
    overridden_by: Optional[str] = None     # variable d'environnement prioritaire


class SecretsResponse(BaseModel):
    file: str                               # chemin affiché (relatif au projet si possible)
    external: bool                          # True : fichier désigné par HYDRA_SECRETS_FILE
    exists: bool
    secrets: List[SecretInfo]


class SecretSet(BaseModel):
    project_id: str
    name: str
    value: str


def _root(project_id: str) -> Path:
    if not store.get_project(project_id):
        raise HTTPException(404, detail=f"Project '{project_id}' not found")
    return store._resolve_project_path(project_id)


def _describe(root: Path) -> SecretsResponse:
    import os
    f = secrets_file_for(root)
    try:
        shown = f.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        shown = str(f)
    names: List[str] = []
    if f.is_file():
        try:
            names = list(load_secrets_file(f))
        except SecretResolutionError as e:
            raise HTTPException(422, detail=str(e))
    return SecretsResponse(
        file=shown, external=bool(os.environ.get(SECRETS_FILE_ENV)), exists=f.is_file(),
        secrets=[SecretInfo(name=n, overridden_by=env_override(n)) for n in names],
    )


@router.get("", response_model=SecretsResponse)
def list_secrets(project_id: str = Query(...)):
    return _describe(_root(project_id))


@router.put("", response_model=SecretsResponse)
def put_secret(body: SecretSet):
    root = _root(body.project_id)
    try:
        set_secret(secrets_file_for(root), body.name, body.value)
    except SecretResolutionError as e:
        raise HTTPException(422, detail=str(e))
    return _describe(root)


@router.delete("/{name}", response_model=SecretsResponse)
def remove_secret(name: str, project_id: str = Query(...)):
    root = _root(project_id)
    if not delete_secret(secrets_file_for(root), name):
        raise HTTPException(404, detail=f"Secret '{name}' not found")
    return _describe(root)
