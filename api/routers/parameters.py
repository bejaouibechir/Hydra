"""
api/routers/parameters.py — Authoring des PARAMÈTRES d'un projet.

Lit/écrit, à la racine du projet :
  - parameters.yaml            (déclarations : name -> {type, default, required, description})
  - environments/<env>.yaml    (valeurs par environnement : name -> value)

Aligné sur la couche de résolution du runner (internal/config/parameters.py).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api import store
from internal.fs_atomic import atomic_write_text

router = APIRouter()


def _proj_root(project_id: str) -> Path:
    proj = store.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    return Path(proj.path)


def _read_block(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    if isinstance(data, dict):
        block = data.get("parameters", data)
        return block if isinstance(block, dict) else {}
    return {}


class ParametersResponse(BaseModel):
    declarations: Dict[str, Any] = {}
    environments: Dict[str, Dict[str, Any]] = {}


class ParametersPayload(BaseModel):
    project_id: str
    declarations: Dict[str, Any] = {}
    environments: Dict[str, Dict[str, Any]] = {}


def _load(root: Path) -> ParametersResponse:
    declarations = _read_block(root / "parameters.yaml")
    environments: Dict[str, Dict[str, Any]] = {}
    env_dir = root / "environments"
    if env_dir.is_dir():
        for f in sorted(env_dir.glob("*.yaml")):
            environments[f.stem] = _read_block(f)
    return ParametersResponse(declarations=declarations, environments=environments)


@router.get("", response_model=ParametersResponse)
def get_parameters(project_id: str = Query(...)) -> ParametersResponse:
    return _load(_proj_root(project_id))


@router.put("", response_model=ParametersResponse)
def save_parameters(body: ParametersPayload) -> ParametersResponse:
    root = _proj_root(body.project_id)
    try:
        if not root.exists():
            raise HTTPException(
                status_code=400,
                detail=f"Dossier projet introuvable sur disk : {root}",
            )
        atomic_write_text(
            root / "parameters.yaml",
            yaml.safe_dump({"parameters": body.declarations}, sort_keys=False, allow_unicode=True),
        )
        env_dir = root / "environments"
        env_dir.mkdir(parents=True, exist_ok=True)
        for name, values in body.environments.items():
            safe = "".join(c for c in name if c.isalnum() or c in ("-", "_")) or "default"
            atomic_write_text(
                env_dir / f"{safe}.yaml",
                yaml.safe_dump({"parameters": values or {}}, sort_keys=False, allow_unicode=True),
            )
        return _load(root)
    except HTTPException:
        raise
    except Exception as e:  # remonte la vraie cause au lieu du 500 générique
        raise HTTPException(
            status_code=500,
            detail=f"Echec sauvegarde paramètres ({type(e).__name__}): {e}",
        ) from e
