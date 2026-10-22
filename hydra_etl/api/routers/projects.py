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
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/{project_id}/unlist", response_model=MessageResponse)
def unlist_project(project_id: str):
    """Retire UNIQUEMENT le raccourci de la liste — ne touche JAMAIS au disk.

    Endpoint volontairement séparé de DELETE : une action sans risque ne doit
    jamais partager sa route avec une action destructrice (si le backend est
    obsolète, l'appel échoue en 404 au lieu de supprimer des fichiers).
    """
    store.delete_project(project_id, remove_files=False)
    return {"message": f"Project '{project_id}' retiré de la liste (fichiers intacts)"}


@router.delete("/{project_id}", response_model=MessageResponse)
def delete_project(project_id: str, remove_files: bool = True):
    """remove_files=False → retire le raccourci seul ; True → + dossier disk.
    Idempotent : ne renvoie jamais 404 — le retrait est toujours effectif."""
    store.delete_project(project_id, remove_files=remove_files)
    return {"message": f"Project '{project_id}' deleted (files={'yes' if remove_files else 'kept'})"}
