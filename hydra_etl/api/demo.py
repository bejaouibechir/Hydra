"""api/demo.py — projet de démonstration livré avec le package.

Le gabarit (hydra_etl/samples/hydra-demo) contient des jobs CSV/JSON → CSV dont
les fichiers d'entrée sont déjà en place. À l'installation il est copié dans le
workspace, avec les chemins réécrits en absolu, puis enregistré comme un projet
ordinaire.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional

from hydra_etl.api import store
from hydra_etl.api.models import ProjectResponse

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "samples" / "hydra-demo"
DEMO_NAME = "hydra-demo"
_TOKEN = "__HYDRA_DEMO_ROOT__"
_TEXT_SUFFIXES = {".yaml", ".yml"}


def _seeded_flag() -> Path:
    return store.WORKSPACE / ".demo_seeded"


def install_demo_project() -> Optional[ProjectResponse]:
    """Copie le gabarit dans le workspace et l'enregistre. None si gabarit absent."""
    if not TEMPLATE_DIR.is_dir():
        return None
    dest = store.WORKSPACE / DEMO_NAME
    n = 2
    while dest.exists():
        dest = store.WORKSPACE / f"{DEMO_NAME}-{n}"
        n += 1
    shutil.copytree(TEMPLATE_DIR, dest, ignore=shutil.ignore_patterns("__pycache__", ".hydra"))
    # Même structure qu'un projet de `hdrctl init` (les dossiers vides ne
    # voyagent pas dans le paquet).
    for sub in ("outputs", "environments", "scripts"):
        (dest / sub).mkdir(exist_ok=True)

    root = dest.resolve().as_posix()          # '/' accepté aussi sous Windows
    for f in dest.rglob("*"):
        if f.is_file() and f.suffix in _TEXT_SUFFIXES:
            txt = f.read_text(encoding="utf-8")
            if _TOKEN in txt:
                f.write_text(txt.replace(_TOKEN, root), encoding="utf-8")

    proj = store.open_project(str(dest), adopt=True)
    from hydra_etl.internal.config.secrets import scaffold_secrets
    scaffold_secrets(dest)                     # .hydra/secrets + .gitignore
    try:
        _seeded_flag().write_text("1", encoding="utf-8")
    except OSError:
        pass
    return proj


def seed_on_first_run() -> Optional[ProjectResponse]:
    """Installe la démo une seule fois, si aucun projet n'existe.

    Jamais recréée après suppression (drapeau `.demo_seeded`).
    Désactivable avec HYDRA_NO_DEMO=1.
    """
    if os.environ.get("HYDRA_NO_DEMO") == "1":
        return None
    if _seeded_flag().exists():
        return None
    if store.list_projects():
        return None
    return install_demo_project()
