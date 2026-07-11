"""
api/routers/jobs.py — Bridge CLI → API pour les commandes job Hydra.

Expose les opérations de la CLI (run, validate, test, list, init)
comme endpoints REST — utilisables directement par le Studio.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api import store

router = APIRouter()


class JobFilesResponse(BaseModel):
    name: str
    sources: str
    transformations: str
    destinations: str
    pipeline: str


@router.get("/files", response_model=JobFilesResponse)
def get_job_files(project_id: str, name: str):
    """Lit les 4 fichiers YAML d'un job sur disk — chargement du canvas Studio."""
    proj = store.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    job_dir = Path(proj.path) / "jobs" / name
    if not job_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Job '{name}' introuvable dans {proj.path}/jobs/")

    def _read(fname: str) -> str:
        f = job_dir / fname
        try:
            return f.read_text(encoding="utf-8") if f.exists() else ""
        except Exception:
            return ""

    return JobFilesResponse(
        name=name,
        sources=_read("sources.yaml"),
        transformations=_read("transformations.yaml"),
        destinations=_read("destinations.yaml"),
        pipeline=_read("pipeline.yaml"),
    )


class JobRunRequest(BaseModel):
    path: str
    dry_run: bool = False
    verbosity: int = 1
    sources_file: Optional[str] = None
    destinations_file: Optional[str] = None
    pipeline_file: Optional[str] = None
    transformations_file: Optional[str] = None
    on_success: Optional[str] = None
    on_failure: Optional[str] = None
    on_finish: Optional[str] = None


class JobValidateRequest(BaseModel):
    path: str
    strict: bool = False


class JobTestRequest(BaseModel):
    path: str
    only_sources: bool = False
    only_destinations: bool = False
    only_transform: bool = False


class JobInitRequest(BaseModel):
    name: str
    template: str = "basic"
    force: bool = False


class ScaffoldTransform(BaseModel):
    op: str                        # filter | select | rename | cast | derive | sort
    params: dict = {}


class JobScaffoldRequest(BaseModel):
    job_name:        str
    base_dir:        str
    source_type:     str = "csv"
    source_path:     str
    transformations: list[ScaffoldTransform] = []
    dest_type:       str = "csv"
    dest_path:       str
    dest_mode:       str = "replace"


class JobScaffoldResponse(BaseModel):
    job_path: str
    created:  bool


class CLIResult(BaseModel):
    returncode: int
    stdout: str
    stderr: str
    success: bool


def _run_cli(*args: str) -> CLIResult:
    """Exécute une commande hdrctl en subprocess."""
    cmd = [sys.executable, "-m", "cli.hdrctl"] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return CLIResult(
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
        success=result.returncode == 0,
    )


@router.post("/run", response_model=CLIResult)
def run_job(body: JobRunRequest):
    """Exécute un job Hydra (équivalent `hdrctl run`)."""
    args = ["run", body.path]
    if body.dry_run:
        args.append("--dry-run")
    for flag, val in [
        ("-s", body.sources_file),
        ("-d", body.destinations_file),
        ("-p", body.pipeline_file),
        ("-t", body.transformations_file),
        ("--on-success", body.on_success),
        ("--on-failure", body.on_failure),
        ("--on-finish", body.on_finish),
    ]:
        if val:
            args += [flag, val]
    if body.verbosity == 1:
        args.append("-v")
    elif body.verbosity == 2:
        args.append("-vv")
    elif body.verbosity >= 3:
        args.append("-vvv")
    return _run_cli(*args)


@router.post("/validate", response_model=CLIResult)
def validate_job(body: JobValidateRequest):
    """Valide les YAML d'un job (équivalent `hdrctl validate`)."""
    args = ["validate", body.path]
    if body.strict:
        args.append("--strict")
    return _run_cli(*args)


@router.post("/test", response_model=CLIResult)
def test_job(body: JobTestRequest):
    """Teste les connexions d'un job (équivalent `hdrctl test`)."""
    args = ["test", body.path]
    if body.only_sources:
        args.append("--only-sources")
    if body.only_destinations:
        args.append("--only-destinations")
    if body.only_transform:
        args.append("--only-transform")
    return _run_cli(*args)


@router.get("/list", response_model=CLIResult)
def list_jobs(path: str = "."):
    """Liste les jobs dans un dossier (équivalent `hdrctl list`)."""
    return _run_cli("list", path)


@router.post("/scaffold", response_model=JobScaffoldResponse)
def scaffold_job(body: JobScaffoldRequest):
    """Crée un job complet (4 fichiers YAML) depuis l'interface Studio."""
    import yaml as _yaml
    from pathlib import Path as _Path

    job_dir = _Path(body.base_dir) / body.job_name
    job_dir.mkdir(parents=True, exist_ok=True)

    src_id  = f"source_{body.job_name}"
    dest_id = f"dest_{body.job_name}"

    # Construire les steps de transformation
    steps = [{t.op: t.params} for t in body.transformations]

    files: dict = {
        "sources.yaml": {
            "version": "1.0",
            "sources": {
                src_id: {
                    "type": body.source_type,
                    "connection": {},
                    "extract": {"table": body.source_path},
                }
            },
        },
        "transformations.yaml": {
            "version": "1.0",
            "transformations": {"steps": steps},
        },
        "destinations.yaml": {
            "version": "1.0",
            "destinations": {
                dest_id: {
                    "type": body.dest_type,
                    "connection": {},
                    "load": {"table": body.dest_path, "mode": body.dest_mode},
                }
            },
        },
        "pipeline.yaml": {
            "version": "1.0",
            "pipeline": {
                "name": body.job_name,
                "from": src_id,
                "to": dest_id,
                "transformations": "transformations",
            },
        },
    }

    for fname, data in files.items():
        with open(job_dir / fname, "w", encoding="utf-8") as f:
            _yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    return JobScaffoldResponse(job_path=str(job_dir), created=True)


@router.post("/init", response_model=CLIResult)
def init_job(body: JobInitRequest):
    """Scaffold un nouveau job (équivalent `hdrctl init`)."""
    args = ["init", body.name, "--template", body.template]
    if body.force:
        args.append("--force")
    return _run_cli(*args)


# --- Workflow CLI bridge ---

class WorkflowRunRequest(BaseModel):
    path: str = "./workflow.yaml"


class WorkflowValidateRequest(BaseModel):
    path: str = "./workflow.yaml"


class WorkflowInitRequest(BaseModel):
    name: str
    template: str = "basic"
    force: bool = False


@router.post("/workflow/run", response_model=CLIResult)
def run_workflow_cli(body: WorkflowRunRequest):
    """Lance un workflow via CLI (équivalent `hdrctl workflow run`)."""
    return _run_cli("workflow", "run", body.path)


@router.post("/workflow/validate", response_model=CLIResult)
def validate_workflow_cli(body: WorkflowValidateRequest):
    """Valide un workflow.yaml (équivalent `hdrctl workflow validate`)."""
    return _run_cli("workflow", "validate", body.path)


@router.get("/workflow/list", response_model=CLIResult)
def list_workflows_cli(path: str = "."):
    """Liste les workflows dans un dossier (équivalent `hdrctl workflow list`)."""
    return _run_cli("workflow", "list", path)


@router.post("/workflow/init", response_model=CLIResult)
def init_workflow_cli(body: WorkflowInitRequest):
    """Scaffold un nouveau workflow (équivalent `hdrctl workflow init`)."""
    args = ["workflow", "init", body.name, "--template", body.template]
    if body.force:
        args.append("--force")
    return _run_cli(*args)
