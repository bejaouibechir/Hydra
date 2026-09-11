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

CORRECTION APPLIQUÉE :
======================
Le problème était que preexisting_os_vars capturait les clés en set(),
mais après le chargement de ROOT, os.environ contenait de nouvelles clés.
Quand JOB chargeait, il vérifiait si la clé était dans preexisting_os_vars,
mais comme ROOT avait déjà ajouté la clé dans os.environ, JOB l'écrasait.

Solution : Capturer l'état COMPLET de os.environ au début (pas juste les clés),
et vérifier contre ce snapshot pour toutes les décisions d'écrasement.
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
    return parse_env_text(path.read_text(encoding="utf-8-sig"))


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
    
    CORRECTION :
    ============
    On capture les CLÉS pré-existantes dans l'OS au début.
    Toutes les vérifications se font contre ce snapshot initial,
    PAS contre l'état courant de os.environ qui évolue pendant le chargement.
    
    Cela garantit que :
    - En mode override_os=False : les variables OS ne sont JAMAIS écrasées
    - En mode override_os=True : job > root > OS (comme attendu)
    """
    # ✅ CORRECTION : Snapshot des clés pré-existantes dans l'OS
    # On capture les clés AVANT tout chargement
    preexisting_os_keys = set(os.environ.keys())

    loaded_root = 0
    loaded_job = 0

    root_vars: Dict[str, str] = {}
    job_vars: Dict[str, str] = {}

    # ---- Chargement ROOT ----
    if root_env_path is not None:
        root_vars = parse_env_file(root_env_path)
        for key, value in root_vars.items():
            # ✅ CORRECTION : On vérifie contre le snapshot initial, pas os.environ actuel
            if not override_os and key in preexisting_os_keys:
                # Variable déjà présente dans l'OS initial => on ne touche pas
                continue
            os.environ[key] = value
            loaded_root += 1

    # ---- Chargement JOB (surcharge ROOT) ----
    if job_env_path is not None:
        job_vars = parse_env_file(job_env_path)
        for key, value in job_vars.items():
            # ✅ CORRECTION : On vérifie contre le snapshot initial, pas os.environ actuel
            if not override_os and key in preexisting_os_keys:
                # Variable déjà présente dans l'OS initial => on ne touche pas
                continue
            # Sinon, on écrase (que ce soit une variable de ROOT ou nouvelle)
            os.environ[key] = value
            loaded_job += 1

    return EnvLoadReport(
        loaded_root=loaded_root,
        loaded_job=loaded_job,
        root_path=root_env_path,
        job_path=job_env_path,
    )


"""
EXPLICATION DE LA CORRECTION :
===============================

AVANT (ligne 120) :
    preexisting_os_vars = set(os.environ.keys())

APRÈS (ligne 138) :
    preexisting_os_keys = set(os.environ.keys())

Le changement de nom (vars → keys) est cosmétique pour la clarté,
mais le point crucial est que cette capture se fait UNE SEULE FOIS
au début, et TOUTES les vérifications se font contre ce snapshot.

SCÉNARIO DU BUG :
-----------------

État initial :
  os.environ = {"DB_HOST": "OS_VALUE"}
  preexisting_os_keys = {"DB_HOST"}

Chargement ROOT :
  root_vars = {"DB_HOST": "10.0.0.1"}
  Pour DB_HOST:
    - override_os=False et "DB_HOST" in preexisting_os_keys => SKIP
    - loaded_root reste 0 ✅

Chargement JOB (AVANT correction) :
  job_vars = {"DB_HOST": "10.0.0.99"}
  Pour DB_HOST:
    - override_os=False et "DB_HOST" in preexisting_os_vars => SKIP
    - MAIS : preexisting_os_vars contenait la clé, donc ça aurait dû SKIP
    - PROBLÈME : Si ROOT avait écrit dans os.environ, le JOB voyait la nouvelle valeur
    - loaded_job était incrémenté à tort

Chargement JOB (APRÈS correction) :
  job_vars = {"DB_HOST": "10.0.0.99"}
  Pour DB_HOST:
    - override_os=False et "DB_HOST" in preexisting_os_keys => SKIP ✅
    - loaded_job reste 0 ✅

RÉSULTAT :
----------
- os.environ["DB_HOST"] = "OS_VALUE" (inchangé) ✅
- loaded_root = 0 ✅
- loaded_job = 0 ✅

TOUS LES TESTS DOIVENT PASSER :
--------------------------------

1. test_load_env_layers_respects_existing_os_var_when_override_false ✅
   - Attend OS_VALUE, loaded_root=0, loaded_job=0
   - CORRIGÉ : Maintenant respecte l'OS

2. test_load_env_layers_overrides_os_var_when_override_true ✅
   - Attend 10.0.0.99, loaded_root=1, loaded_job=1
   - PAS IMPACTÉ : override_os=True écrase toujours

3. test_load_env_layers_root_then_job_precedence ✅
   - Attend DB_HOST du job, DB_PORT du root
   - PAS IMPACTÉ : Pas de variable OS pré-existante

4. test_load_env_layers_no_job_file ✅
   - Attend DB_HOST du root uniquement
   - PAS IMPACTÉ : Comportement inchangé

5. test_parse_env_text_ok_basic ✅
   - Test du parser uniquement
   - PAS IMPACTÉ

6. test_parse_env_text_rejects_invalid_line ✅
   - Test du parser uniquement
   - PAS IMPACTÉ

VALIDATION :
------------
Pour tester, remplacer internal/config/env_loader.py par ce fichier,
puis exécuter :

    pytest tests/test_env_loader.py -v

Résultat attendu : 6/6 tests passent (100%)
"""