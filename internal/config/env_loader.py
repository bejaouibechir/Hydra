"""
Chargement de variables d'environnement depuis des fichiers .env.

Objectif :
- Supporter 2 niveaux :
  1) .env à la racine du projet (valeurs par défaut)
  2) .env au niveau du job (surcharge)

Règles de priorité :
- Si override_os=False :
    OS existant > .env job > .env root
- Si override_os=True :
    .env job > .env root > OS existant

Ce module est volontairement simple :
- pas de dépendance externe (pas de python-dotenv)
- pas de substitution (${...})
- uniquement injection dans os.environ
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional


class EnvFileParseError(ValueError):
    """Erreur de parsing d'un fichier .env."""
    pass


@dataclass(frozen=True)
class EnvLoadReport:
    """
    Rapport de chargement (utile pour tests et debug).
    """
    loaded_root: int
    loaded_job: int
    root_path: Optional[Path]
    job_path: Optional[Path]


def _strip_quotes(value: str) -> str:
    """
    Supprime les guillemets simples ou doubles englobants, si présents.
    """
    v = value.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
        return v[1:-1]
    return v


def parse_env_text(text: str) -> Dict[str, str]:
    """
    Parse le contenu texte d'un fichier .env.

    Support :
    - lignes vides
    - commentaires (#)
    - KEY=VALUE
    - export KEY=VALUE
    - valeurs avec ou sans quotes
    """
    out: Dict[str, str] = {}

    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()

        if not line or line.startswith("#"):
            continue

        if line.startswith("export "):
            line = line[len("export ") :].strip()

        if "=" not in line:
            raise EnvFileParseError(
                f"Ligne .env invalide (pas de '=') à la ligne {lineno}: {raw_line}"
            )

        key, value = line.split("=", 1)
        key = key.strip()
        value = _strip_quotes(value.strip())

        if not key:
            raise EnvFileParseError(
                f"Clé .env vide à la ligne {lineno}: {raw_line}"
            )

        out[key] = value

    return out


def parse_env_file(path: Path) -> Dict[str, str]:
    """
    Parse un fichier .env.
    Si le fichier n'existe pas, retourne {}.
    """
    if not path.exists():
        return {}
    return parse_env_text(path.read_text(encoding="utf-8"))


def load_env_layers(
    *,
    root_env_path: Optional[Path],
    job_env_path: Optional[Path],
    override_os: bool = False,
) -> EnvLoadReport:
    """
    Charge les variables d'environnement depuis :
    - .env root
    - .env job

    L'environnement OS initial est snapshoté pour garantir
    le respect strict des priorités.
    """
    preexisting_os_vars = set(os.environ.keys())

    loaded_root = 0
    loaded_job = 0

    root_vars: Dict[str, str] = {}
    job_vars: Dict[str, str] = {}

    # ---- Chargement ROOT ----
    if root_env_path is not None:
        root_vars = parse_env_file(root_env_path)
        for key, value in root_vars.items():
            if not override_os and key in preexisting_os_vars:
                continue
            os.environ[key] = value
            loaded_root += 1

    # ---- Chargement JOB (surcharge ROOT) ----
    if job_env_path is not None:
        job_vars = parse_env_file(job_env_path)
        for key, value in job_vars.items():
            if not override_os and key in preexisting_os_vars:
                continue
            os.environ[key] = value
            loaded_job += 1

    return EnvLoadReport(
        loaded_root=loaded_root,
        loaded_job=loaded_job,
        root_path=root_env_path,
        job_path=job_env_path,
    )
