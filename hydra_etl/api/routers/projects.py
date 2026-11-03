"""api/routers/projects.py — CRUD projets."""
from typing import List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from hydra_etl.api import store
from hydra_etl.api.models import MessageResponse, ProjectCreate, ProjectOpenRequest, ProjectResponse

router = APIRouter()


@router.get("", response_model=List[ProjectResponse])
def list_projects():
    """Liste tous les projets du workspace."""
    return store.list_projects()


@router.post("", response_model=ProjectResponse, status_code=201)
def create_project(body: ProjectCreate):
    """Crée un nouveau projet (dossier sur disk)."""
    return store.create_project(name=body.name, description=body.description, project_path=body.project_path)


@router.post("/demo", response_model=ProjectResponse, status_code=201)
def install_demo():
    """Installe (ou réinstalle) le projet de démonstration."""
    from hydra_etl.api import demo
    proj = demo.install_demo_project()
    if proj is None:
        raise HTTPException(status_code=404, detail="Demo template not found")
    return proj


@router.post("/open", response_model=ProjectResponse)
def open_project(body: ProjectOpenRequest):
    """Ouvre un projet depuis le disk.

    adopt=True  → dossier quelconque accepté (adoption : project.yaml créé)
    adopt=False → exige un projet Hydra existant, sinon 400
    """
    try:
        proj = store.open_project(body.path, adopt=body.adopt)
    except store.NotAHydraProject:
        raise HTTPException(
            status_code=400,
            detail="Ce dossier n'a pas la structure d'un projet Hydra "
                   "(aucun workflow dans workflows/ ni job dans jobs/). "
                   "Utilisez « Ouvrir un dossier local » pour l'adopter comme projet.")
    if not proj:
        raise HTTPException(status_code=404, detail=f"Chemin introuvable : {body.path}")
    # Les workflows `trigger: schedule` du projet ouvert sont planifiés tout de
    # suite (sinon seulement au prochain démarrage de hdrctl serve).
    try:
        from hydra_etl.api import scheduler, trigger_service
        scheduler.sync_all()
        trigger_service.sync()           # ses déclencheurs (triggers.yaml) aussi
    except Exception:  # noqa: BLE001 — la planification ne doit pas empêcher l'ouverture
        pass
    return proj


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str):
    proj = store.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    return proj


class CardOrder(BaseModel):
    order: List[str]                     # ids des workflows, dans l'ordre d'affichage


@router.put("/{project_id}/card-order", response_model=CardOrder)
def set_card_order(project_id: str, body: CardOrder):
    """Ordre des cartes de workflows sur la page projet (glisser-déposer).
    Purement visuel : thread.yaml et hdrctl run ne changent pas."""
    if not store.get_project(project_id):
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    try:
        return CardOrder(order=store.set_card_order(project_id, body.order))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))  # dossier introuvable


def _sync_triggers() -> None:
    """Un projet retiré de la liste n'a plus ses déclencheurs suivis par serve."""
    try:
        from hydra_etl.api import trigger_service
        trigger_service.sync()
    except Exception:  # noqa: BLE001
        pass


@router.post("/{project_id}/unlist", response_model=MessageResponse)
def unlist_project(project_id: str):
    """Retire UNIQUEMENT le raccourci de la liste — ne touche JAMAIS au disk.

    Endpoint volontairement séparé de DELETE : une action sans risque ne doit
    jamais partager sa route avec une action destructrice (si le backend est
    obsolète, l'appel échoue en 404 au lieu de supprimer des fichiers).
    """
    store.delete_project(project_id, remove_files=False)
    _sync_triggers()
    return {"message": f"Project '{project_id}' retiré de la liste (fichiers intacts)"}


@router.delete("/{project_id}", response_model=MessageResponse)
def delete_project(project_id: str, remove_files: bool = True):
    """remove_files=False → retire le raccourci seul ; True → + dossier disk.
    Idempotent : ne renvoie jamais 404 — le retrait est toujours effectif."""
    store.delete_project(project_id, remove_files=remove_files)
    _sync_triggers()
    return {"message": f"Project '{project_id}' deleted (files={'yes' if remove_files else 'kept'})"}


# ── Step type: project (Studio : nœud Project) ──────────────────────────────

class ProjectStepCheck(BaseModel):
    project: str                                 # chemin (ref: path) ou nom (ref: name)
    ref: str = "path"
    workflows: List[str] = []


@router.post("/{project_id}/project-step")
def check_project_step(project_id: str, body: ProjectStepCheck):
    """Projet appelé par un step type: project du projet `project_id` : ce qu'il
    déclare (paramètres, workflows, environnements) et les problèmes qu'un tel
    step créerait (introuvable, cycle, profondeur). Rien n'est écrit."""
    import os
    from pathlib import Path
    from hydra_etl.internal.config.env_admin import list_environments, read_parameters
    from hydra_etl.workflow.project import workflow_files
    from hydra_etl.workflow.subprojects import (
        ProjectRefError, _project_name, check_new_call, resolve_project,
    )
    master = store.get_project(project_id)
    if not master:
        raise HTTPException(404, detail=f"Project '{project_id}' not found")
    root = Path(master.path).resolve()
    out = {"ok": False, "errors": [], "warnings": [], "tree": [], "name": None, "path": None,
           "relative": None, "project_id": None, "workflows": [], "parameters": {},
           "environments": []}
    try:
        target = resolve_project(body.project, root, body.ref if body.ref in ("path", "name") else "path")
    except ProjectRefError as e:
        out["errors"].append(str(e))
        return out
    out["name"] = _project_name(target)
    out["path"] = str(target)
    try:
        out["relative"] = Path(os.path.relpath(target, root)).as_posix()
    except ValueError:                               # autre lecteur (Windows)
        out["relative"] = target.as_posix()
    for p in store.list_projects():
        try:
            if Path(p.path).resolve() == target:
                out["project_id"] = p.id
                break
        except OSError:
            continue
    out["workflows"] = sorted(n for n in workflow_files(target) if n != "thread")
    try:
        out["parameters"] = read_parameters(target).declarations
    except Exception:  # noqa: BLE001
        out["parameters"] = {}
    out["environments"] = [e.name for e in list_environments(target)]
    unknown = [w for w in body.workflows if w not in out["workflows"]]
    if unknown:
        out["errors"].append(f"workflow(s) not found in {out['name']}: {', '.join(unknown)}")
    res = check_new_call(root, target, body.workflows or None)
    out["errors"] += res.errors
    out["warnings"] += res.warnings
    out["tree"] = [{"depth": d, "label": lbl} for d, lbl in res.tree]
    out["ok"] = not out["errors"]
    return out
