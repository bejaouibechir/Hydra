"""
api/models.py — Schémas Pydantic pour l'API Hydra.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------

class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    project_path: Optional[str] = None   # chemin custom (ex: D:/monprojet) — sinon HYDRA_WORKSPACE/uuid


class ProjectOpenRequest(BaseModel):
    path: str                            # dossier du projet
    adopt: bool = True                   # False → exige la structure projet (workflows/ ou jobs/)


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    path: str
    created_at: str


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------

class WorkflowCreate(BaseModel):
    name: str
    project_id: str
    description: Optional[str] = None
    trigger_type: Literal["manual", "schedule", "webhook"] = "manual"
    cron: Optional[str] = None


class JobFilesPayload(BaseModel):
    """Les 4 fichiers YAML d'un job, sérialisés depuis le canvas Studio."""
    name: str                                     # nom du job (slugifié → dossier jobs/<name>/)
    sources: str                                  # contenu sources.yaml
    transformations: str                          # contenu transformations.yaml
    destinations: str                             # contenu destinations.yaml
    pipeline: str                                 # contenu pipeline.yaml


class WorkflowUpdate(BaseModel):
    description: Optional[str] = None
    trigger_type: Optional[Literal["manual", "schedule", "webhook"]] = None
    cron: Optional[str] = None
    published: Optional[bool] = None
    layout: Optional[Dict[str, Any]] = None      # canvas positions XY
    yaml_content: Optional[str] = None            # contenu workflow.yaml sérialisé depuis le canvas
    jobs: Optional[List[JobFilesPayload]] = None  # jobs à matérialiser sur disk (jobs/<name>/*.yaml)


class WorkflowResponse(BaseModel):
    id: str
    name: str
    project_id: str
    description: Optional[str] = None
    trigger_type: str
    cron: Optional[str] = None
    published: bool
    path: str
    layout: Optional[Dict[str, Any]] = None
    yaml_content: Optional[str] = None            # contenu workflow.yaml (lecture seule, GET détail)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

class RunRequest(BaseModel):
    workflow_path: str                            # chemin vers workflow.yaml
    env: Optional[str] = "default"               # environnement cible
    step: Optional[str] = None                   # si present -> run jusqu'a ce step


class InlineJobRequest(BaseModel):
    hdr_content: str                             # contenu YAML .hdr complet
    job_name: Optional[str] = "inline_job"       # nom affiche dans les logs
    work_dir: Optional[str] = None               # repertoire de travail (resolution chemins relatifs)
    env: Optional[str] = "default"
    preview_up_to: Optional[int] = None          # index max de transformation à exécuter (preview partiel)


class PeekRequest(BaseModel):
    """Lecture directe du top N d'une destination (fichier ou base) — sans re-run."""
    dest: Dict[str, Any]                          # config destination : {type, path?, connection?, table?, delimiter?}
    limit: int = 10                              # nombre de lignes a lire
    work_dir: Optional[str] = None               # base de resolution des chemins relatifs


class RunResponse(BaseModel):
    run_id: str
    workflow_name: str
    workflow_path: Optional[str] = None            # chemin complet -- requis pour re-run
    status: Literal["pending", "running", "success", "failed"]
    started_at: str
    finished_at: Optional[str] = None
    duration: Optional[float] = None
    error: Optional[str] = None
    steps: List[Dict[str, Any]] = Field(default_factory=list)
    trigger: Optional[str] = "manual"     # manual | schedule | webhook -- source du run


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

class EnvironmentCreate(BaseModel):
    name: str
    project_id: str
    vars: Dict[str, str] = Field(default_factory=dict)


class EnvironmentUpdate(BaseModel):
    vars: Optional[Dict[str, str]] = None


class EnvironmentResponse(BaseModel):
    id: str
    name: str
    project_id: str
    vars: Dict[str, str]


# ---------------------------------------------------------------------------
# Node catalogue
# ---------------------------------------------------------------------------

class NodeInfo(BaseModel):
    id: str
    name: str
    category: Literal["source", "destination", "transformation", "action"]
    description: str
    config_schema: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Generic
# -------------------------------------------------------------------

class MessageResponse(BaseModel):
    message: str


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

class ExportRequest(BaseModel):
    content: str
    suggested_name: str
    fmt: str = "csv"


class ExportResponse(BaseModel):
    saved: bool
    path: Optional[str] = None
    cancelled: bool = False


# ---------------------------------------------------------------------------
# Action node
# ---------------------------------------------------------------------------

class ActionNodeRequest(BaseModel):
    node_type: str                              # 'action_powershell' | 'action_bash' | 'action_ssh'
    command: str
    working_dir: Optional[str] = None
    timeout: Optional[int] = 60
    job_name: Optional[str] = "action"
    params: Optional[Dict[str, str]] = None    # params SSH : host, port, username, password, key_path
