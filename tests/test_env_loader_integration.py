"""
Tests d’intégration pour env_loader:
- lit de vrais fichiers .env (root + job)
- vérifie les règles de priorité
- vérifie que override_os=False n’écrase PAS l’OS
- vérifie que override_os=True écrase l’OS
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# ⚠️ Adapter l'import à ton arborescence réelle
# Exemple : from internal.config.env_loader import load_env_layers
from internal.config.env_loader import load_env_layers


@pytest.fixture
def fixtures_dir() -> Path:
    """
    Retourne le dossier des fixtures .env.
    """
    return Path(__file__).parent / "fixtures" / "env"


@pytest.fixture
def root_env_path(fixtures_dir: Path) -> Path:
    """
    Chemin du .env root.
    """
    return fixtures_dir / "root" / ".env"


@pytest.fixture
def job_env_path(fixtures_dir: Path) -> Path:
    """
    Chemin du .env du job.
    """
    return fixtures_dir / "job_a" / ".env"


def _unset(keys: list[str]) -> None:
    """
    Supprime proprement une liste de variables d’environnement.
    """
    for k in keys:
        os.environ.pop(k, None)


def test_override_os_false_preserves_os_over_env_files(root_env_path: Path, job_env_path: Path):
    """
    override_os=False :
      OS existant > .env job > .env root

    Cas :
    - OS définit DB_HOST et DB_PORT
    - root définit DB_HOST/DB_PORT/DB_USER
    - job surcharge DB_HOST/DB_USER
    Attendu :
    - DB_HOST reste OS
    - DB_PORT reste OS
    - DB_USER vient du job (car pas défini dans OS)
    """
    keys = ["DB_HOST", "DB_PORT", "DB_USER", "JOB_ONLY", "SHARED_ONLY"]
    _unset(keys)

    # --- On simule des variables OS existantes ---
    os.environ["DB_HOST"] = "os-host"
    os.environ["DB_PORT"] = "9999"

    report = load_env_layers(
        root_env_path=root_env_path,
        job_env_path=job_env_path,
        override_os=False,
    )

    # --- Vérifications priorité ---
    assert os.environ["DB_HOST"] == "os-host"          # OS gagne
    assert os.environ["DB_PORT"] == "9999"             # OS gagne
    assert os.environ["DB_USER"] == "job-user"         # job gagne sur root
    assert os.environ["JOB_ONLY"] == "job-value"       # job-only existe
    assert os.environ["SHARED_ONLY"] == "root-value"   # root-only existe

    # --- Sanity check report ---
    assert report.root_path == root_env_path
    assert report.job_path == job_env_path


def test_override_os_true_env_files_override_os(root_env_path: Path, job_env_path: Path):
    """
    override_os=True :
      .env job > .env root > OS existant

    Cas :
    - OS définit DB_HOST et DB_PORT
    - root définit DB_HOST/DB_PORT/DB_USER
    - job surcharge DB_HOST/DB_USER
    Attendu :
    - DB_HOST vient du job
    - DB_PORT vient du root
    - DB_USER vient du job
    """
    keys = ["DB_HOST", "DB_PORT", "DB_USER", "JOB_ONLY", "SHARED_ONLY"]
    _unset(keys)

    # --- Variables OS existantes ---
    os.environ["DB_HOST"] = "os-host"
    os.environ["DB_PORT"] = "9999"

    report = load_env_layers(
        root_env_path=root_env_path,
        job_env_path=job_env_path,
        override_os=True,
    )

    # --- Vérifications priorité ---
    assert os.environ["DB_HOST"] == "job-host"         # job gagne
    assert os.environ["DB_PORT"] == "3306"             # root gagne sur OS
    assert os.environ["DB_USER"] == "job-user"         # job gagne
    assert os.environ["JOB_ONLY"] == "job-value"
    assert os.environ["SHARED_ONLY"] == "root-value"

    # --- Sanity check report ---
    assert report.root_path == root_env_path
    assert report.job_path == job_env_path


def test_missing_env_files_is_ok(tmp_path: Path):
    """
    Si les fichiers n'existent pas, load_env_layers ne doit pas planter
    et ne doit rien injecter.
    """
    keys = ["DB_HOST", "DB_PORT"]
    _unset(keys)

    missing_root = tmp_path / "missing_root.env"
    missing_job = tmp_path / "missing_job.env"

    report = load_env_layers(
        root_env_path=missing_root,
        job_env_path=missing_job,
        override_os=False,
    )

    assert "DB_HOST" not in os.environ
    assert "DB_PORT" not in os.environ
    assert report.root_path == missing_root
    assert report.job_path == missing_job
