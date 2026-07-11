"""
api/routers/fs.py — Utilitaires filesystem pour le Studio.

Permet au Studio (navigateur) d'obtenir des chemins absolus côté serveur,
nécessaires pour la résolution des chemins relatifs dans les jobs importés.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter

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
