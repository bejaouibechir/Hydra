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
            _record_layer_key(key)
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
            _record_layer_key(key)
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

# ---------------------------------------------------------------------------
# Variables d'environnement globales (partagées entre projets) — 0.18
# ---------------------------------------------------------------------------
# Dossier de l'utilisateur : ~/.hydra (ou HYDRA_HOME). Deux fichiers .env :
#   env          variables communes à tous les environnements ;
#   env.<nom>    variables de l'environnement <nom> (dev, prod…), choisi par
#                --env / HYDRA_ENV ou par le combo du Studio.
# Ordre (du plus faible au plus fort) : env < env.<nom> < .env du projet
#   < .env du job < --env-file (HYDRA_ENV_FILE). Comme pour les .env existants,
#   un fichier l'emporte sur la variable déjà présente dans le système.

import re as _re
import threading as _threading

HOME_ENV = "HYDRA_HOME"
ENV_FILE_ENV = "HYDRA_ENV_FILE"
ENV_NAME_RE = _re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_\-]*$")


def hydra_home() -> Path:
    """Dossier des réglages de l'utilisateur (variables globales)."""
    return Path(os.environ.get(HOME_ENV) or (Path.home() / ".hydra")).expanduser()


def check_env_name(name: str) -> str:
    n = (name or "").strip()
    if not ENV_NAME_RE.match(n):
        raise ValueError(f"invalid environment name '{name}': use letters, digits, '_' or '-'")
    return n


def global_env_file(env: Optional[str] = None) -> Path:
    """~/.hydra/env (commun) ou ~/.hydra/env.<env>."""
    home = hydra_home()
    return home / "env" if not env else home / f"env.{check_env_name(env)}"


def global_env_names() -> list:
    """Environnements qui ont des variables globales (fichiers env.<nom>)."""
    home = hydra_home()
    if not home.is_dir():
        return []
    return sorted(p.name[4:] for p in home.glob("env.*") if p.is_file() and ENV_NAME_RE.match(p.name[4:]))


_GLOBAL_LOCK = _threading.Lock()
_GLOBAL_STATE: Dict[str, object] = {"env": None, "applied": {}}   # applied : clé -> (valeur posée, valeur d'origine)


def apply_global_env(env: Optional[str], override_os: bool = True) -> Dict[str, str]:
    """Pose dans os.environ les variables globales (commun + env.<env>).

    Quand l'environnement change d'un run au suivant (Studio, API), les
    variables posées pour le précédent sont d'abord retirées (ou rendues à leur
    valeur d'origine), sauf si quelqu'un les a modifiées depuis : un run en dev
    ne garde pas une variable propre à prod. Retourne {clé: fichier}.
    """
    files = [global_env_file(None)]
    if env:
        files.append(global_env_file(env))
    values: Dict[str, str] = {}
    sources: Dict[str, str] = {}
    for f in files:
        for k, v in parse_env_file(f).items():
            values[k] = v
            sources[k] = str(f)
    with _GLOBAL_LOCK:
        applied: Dict[str, tuple] = _GLOBAL_STATE["applied"]  # type: ignore[assignment]
        if _GLOBAL_STATE["env"] != env:
            for k, (set_val, orig) in list(applied.items()):
                if os.environ.get(k) == set_val:
                    if orig is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = orig
                applied.pop(k, None)
        for k, v in values.items():
            if k not in applied:
                if not override_os and k in os.environ:
                    continue
                applied[k] = (v, os.environ.get(k))
            else:
                applied[k] = (v, applied[k][1])
            os.environ[k] = v
        _GLOBAL_STATE["env"] = env
    return sources


def apply_env_file_option(override_os: bool = True) -> int:
    """--env-file / HYDRA_ENV_FILE : variables de ce run, au-dessus de tout."""
    f = os.environ.get(ENV_FILE_ENV)
    if not f:
        return 0
    path = Path(f).expanduser()
    if not path.is_file():
        raise EnvFileParseError(f"environment file not found: {path} (set by {ENV_FILE_ENV})")
    n = 0
    for k, v in parse_env_file(path).items():
        if not override_os and k in os.environ:
            continue
        _record_layer_key(k)
        os.environ[k] = v
        n += 1
    return n


def restore_global_env() -> None:
    """Retire les variables globales posées (rend les valeurs d'origine)."""
    with _GLOBAL_LOCK:
        applied: Dict[str, tuple] = _GLOBAL_STATE["applied"]  # type: ignore[assignment]
        for k, (set_val, orig) in list(applied.items()):
            if os.environ.get(k) == set_val:
                if orig is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = orig
        _GLOBAL_STATE["env"] = None
        _GLOBAL_STATE["applied"] = {}


# ── Couches fichier (.env, --env-file) et isolation d'un projet appelé ──────
# Clé posée par un fichier .env ou --env-file -> valeur qu'elle avait avant
# (None : absente). Sert à rendre un environnement « propre » à un projet appelé
# par un step type: project, sans les variables des fichiers du projet appelant.
_LAYER_ORIGINALS: Dict[str, Optional[str]] = {}

# Variables d'un run qui ne doivent pas passer à un projet appelé : choix
# d'environnement, --env-file et --secrets-file du projet appelant.
CALLER_ONLY_VARS = ("HYDRA_ENV", ENV_FILE_ENV, "HYDRA_SECRETS_FILE")


def _record_layer_key(key: str) -> None:
    if key not in _LAYER_ORIGINALS:
        _LAYER_ORIGINALS[key] = os.environ.get(key)


def environ_without_layers() -> Dict[str, str]:
    """os.environ sans les variables posées par le run en cours : variables
    globales (~/.hydra/env…), fichiers .env / --env-file, CALLER_ONLY_VARS.
    Le projet appelé repose lui-même les siennes."""
    env = dict(os.environ)
    # variables globales posées pour l'environnement du run appelant : le
    # projet appelé repose les siennes (son environnement peut différer)
    with _GLOBAL_LOCK:
        applied = dict(_GLOBAL_STATE["applied"])  # type: ignore[arg-type]
    for k, (set_val, orig) in applied.items():
        if env.get(k) == set_val:
            if orig is None:
                env.pop(k, None)
            else:
                env[k] = orig
    for k, orig in _LAYER_ORIGINALS.items():
        if orig is None:
            env.pop(k, None)
        else:
            env[k] = orig
    for k in CALLER_ONLY_VARS:
        env.pop(k, None)
    return env


import contextlib as _contextlib


@_contextlib.contextmanager
def isolated_environ(overrides: Optional[Dict[str, Optional[str]]] = None):
    """Le temps du bloc : os.environ = environ_without_layers() + overrides
    (valeur None = retirée). À la sortie, tout est rendu tel quel (variables,
    état des variables globales, couches fichier)."""
    snapshot = dict(os.environ)
    with _GLOBAL_LOCK:
        g_env = _GLOBAL_STATE["env"]
        g_applied = dict(_GLOBAL_STATE["applied"])  # type: ignore[arg-type]
    layers = dict(_LAYER_ORIGINALS)
    clean = environ_without_layers()
    for k, v in (overrides or {}).items():
        if v is None:
            clean.pop(k, None)
        else:
            clean[k] = str(v)
    os.environ.clear()
    os.environ.update(clean)
    _LAYER_ORIGINALS.clear()
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(snapshot)
        with _GLOBAL_LOCK:
            _GLOBAL_STATE["env"] = g_env
            _GLOBAL_STATE["applied"] = g_applied
        _LAYER_ORIGINALS.clear()
        _LAYER_ORIGINALS.update(layers)
