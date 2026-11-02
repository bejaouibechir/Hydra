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
    scope: str = "common"                   # "common" ou le nom de l'environnement


class SecretsResponse(BaseModel):
    file: str                               # chemin affiché (relatif au projet si possible)
    external: bool                          # True : fichier désigné par HYDRA_SECRETS_FILE
    exists: bool
    secrets: List[SecretInfo]
    env: Optional[str] = None               # environnement demandé
    env_file: Optional[str] = None          # .hydra/secrets.<env>


class SecretSet(BaseModel):
    project_id: str
    name: str
    value: str
    env: Optional[str] = None               # None : secrets communs


def _root(project_id: str) -> Path:
    if not store.get_project(project_id):
        raise HTTPException(404, detail=f"Project '{project_id}' not found")
    return store._resolve_project_path(project_id)


def _norm_env(env: Optional[str]) -> Optional[str]:
    return None if env in (None, "", "default") else env


def _target(root: Path, env: Optional[str]) -> Path:
    from hydra_etl.internal.config.secrets import env_secrets_file
    env = _norm_env(env)
    if not env:
        return secrets_file_for(root)
    try:
        return env_secrets_file(root, env)
    except ValueError as e:
        raise HTTPException(422, detail=str(e))


def _describe(root: Path, env: Optional[str] = None) -> SecretsResponse:
    import os
    env = _norm_env(env)
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
    infos = [SecretInfo(name=n, overridden_by=env_override(n)) for n in names]
    env_file = None
    if env:
        ef = _target(root, env)
        env_file = f".hydra/{ef.name}"
        env_names: List[str] = []
        if ef.is_file():
            try:
                env_names = list(load_secrets_file(ef))
            except SecretResolutionError as e:
                raise HTTPException(422, detail=str(e))
        infos = [i for i in infos if i.name not in env_names] + [
            SecretInfo(name=n, overridden_by=env_override(n), scope=env) for n in env_names]
        infos.sort(key=lambda i: i.name)
    return SecretsResponse(
        file=shown, external=bool(os.environ.get(SECRETS_FILE_ENV)), exists=f.is_file(),
        secrets=infos, env=env, env_file=env_file,
    )


@router.get("", response_model=SecretsResponse)
def list_secrets(project_id: str = Query(...), env: Optional[str] = None):
    return _describe(_root(project_id), env)


@router.put("", response_model=SecretsResponse)
def put_secret(body: SecretSet):
    root = _root(body.project_id)
    try:
        set_secret(_target(root, body.env), body.name, body.value)
    except SecretResolutionError as e:
        raise HTTPException(422, detail=str(e))
    return _describe(root, body.env)


@router.delete("/{name}", response_model=SecretsResponse)
def remove_secret(name: str, project_id: str = Query(...), env: Optional[str] = None):
    root = _root(project_id)
    try:
        found = delete_secret(_target(root, env), name)
    except SecretResolutionError as e:
        raise HTTPException(422, detail=str(e))
    if not found:
        raise HTTPException(404, detail=f"Secret '{name}' not found")
    return _describe(root, env)
