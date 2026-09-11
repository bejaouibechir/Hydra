"""
api/routers/fs.py — Utilitaires filesystem pour le Studio.

Permet au Studio (navigateur) d'obtenir des chemins absolus côté serveur,
nécessaires pour la résolution des chemins relatifs dans les jobs importés.
"""
from __future__ import annotations

import os
import sys
import string
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()


@router.get("/find-job-folder")
def find_job_folder(name: str) -> dict:
    """
    Cherche un dossier par son nom dans l'arborescence courante.

    Utilisé par le Studio après import "Depuis un dossier" pour obtenir
    le chemin absolu du job (résolution des chemins relatifs lors de l'exécution).

    Stratégie : parcours BFS depuis CWD, profondeur max 5, ignore .git / node_modules.
    """
    cwd = Path.cwd()
    IGNORE = {".git", "node_modules", "__pycache__", ".venv", "venv", "_archive"}

    for root, dirs, _ in os.walk(cwd):
        # Élagage
        dirs[:] = [d for d in dirs if d not in IGNORE and not d.startswith(".")]

        rel_parts = Path(root).relative_to(cwd).parts
        if len(rel_parts) > 5:
            dirs.clear()
            continue

        if Path(root).name == name:
            return {"found": True, "path": str(Path(root))}

    return {"found": False, "path": None}


# ---------------------------------------------------------------------------
# Explorateur de dossiers web (remplace le dialogue natif côté serveur).
# Fonctionne partout : WSL, Docker, serveur distant — aucun display requis.
# ---------------------------------------------------------------------------

@router.get("/roots")
def fs_roots() -> dict:
    """Racines de navigation : lecteurs (Windows) ou Home + / (Unix/WSL)."""
    roots: list[dict] = [{"name": "🏠 Accueil", "path": str(Path.home())}]
    if sys.platform == "win32":
        for letter in string.ascii_uppercase:
            drive = f"{letter}:\\"
            if os.path.exists(drive):
                roots.append({"name": drive, "path": drive})
    else:
        roots.append({"name": "/", "path": "/"})
        # Sous WSL, exposer aussi les disques Windows montés (/mnt/c, ...)
        mnt = Path("/mnt")
        if mnt.is_dir():
            try:
                for child in sorted(mnt.iterdir()):
                    if child.is_dir() and len(child.name) == 1:
                        roots.append({"name": f"/mnt/{child.name}", "path": str(child)})
            except OSError:
                pass
    return {"roots": roots}


@router.get("/list")
def fs_list(
    path: str = Query(..., description="Dossier absolu à lister"),
    dirs_only: bool = Query(False, description="Ne renvoyer que les dossiers"),
    ext: str = Query("", description="Filtre extension pour les fichiers, ex: .csv"),
) -> dict:
    """Liste le contenu d'un dossier. Retourne { path, parent, sep, entries }."""
    try:
        p = Path(path).expanduser()
        if not p.is_absolute():
            p = p.resolve()
        p = p.resolve()
    except Exception as exc:  # chemin invalide
        raise HTTPException(status_code=400, detail=f"Chemin invalide : {exc}")

    if not p.is_dir():
        raise HTTPException(status_code=404, detail=f"Dossier introuvable : {p}")

    ext = ext.lower().strip()
    entries: list[dict] = []
    try:
        children = list(p.iterdir())
    except PermissionError:
        raise HTTPException(status_code=403, detail=f"Accès refusé : {p}")
    except OSError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    for child in children:
        name = child.name
        if name.startswith("."):
            continue  # masquer les éléments cachés
        try:
            is_dir = child.is_dir()
        except OSError:
            continue
        if not is_dir:
            if dirs_only:
                continue
            if ext and not name.lower().endswith(ext):
                continue
        entries.append({"name": name, "path": str(child), "is_dir": is_dir})

    entries.sort(key=lambda e: (not e["is_dir"], e["name"].lower()))
    parent = str(p.parent) if p.parent != p else None
    return {"path": str(p), "parent": parent, "sep": os.sep, "entries": entries}
