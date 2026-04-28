"""
Tests du loader YAML.

But :
- verrouiller le comportement (fichiers manquants, YAML vide, YAML non dict)
- éviter des surprises quand on branchera le parser Pydantic
"""

from __future__ import annotations

from pathlib import Path

import pytest

# YamlConfigLoader a été remplacée par load_env_layers lors du refactoring.
# Ces tests ciblent du code mort — ils sont skippés pour traçabilité.
pytestmark = pytest.mark.skip(reason="YamlConfigLoader supprimée — voir test_env_loader.py")

# Import fictif pour éviter NameError dans les fonctions (tests skippés de toute façon)
YamlConfigLoader = None  # type: ignore


def test_loader_missing_files(tmp_path: Path):
    """
    Si les 3 fichiers attendus ne sont pas présents, on échoue tôt.
    """
    job_dir = tmp_path / "job"
    job_dir.mkdir()

    loader = YamlConfigLoader(str(job_dir))

    with pytest.raises(FileNotFoundError):
        loader.load_job()


def test_loader_loads_three_yamls(tmp_path: Path):
    """
    Vérifie qu'on charge bien 3 dicts dans une structure stable.
    """
    job_dir = tmp_path / "job"
    job_dir.mkdir()

    (job_dir / "sources.yaml").write_text("sources: {}\n", encoding="utf-8")
    (job_dir / "destinations.yaml").write_text("destinations: {}\n", encoding="utf-8")
    (job_dir / "pipeline.yaml").write_text("version: '1.0'\nstages: []\n", encoding="utf-8")

    loader = YamlConfigLoader(str(job_dir))
    data = loader.load_job()

    assert set(data.keys()) == {"sources", "destinations", "pipeline"}
    assert "version" in data["pipeline"]


def test_loader_rejects_non_dict_yaml(tmp_path: Path):
    """
    Si le YAML retourne autre chose qu'un dict (ex: liste), on rejette.
    """
    job_dir = tmp_path / "job"
    job_dir.mkdir()

    (job_dir / "sources.yaml").write_text("- a\n- b\n", encoding="utf-8")
    (job_dir / "destinations.yaml").write_text("destinations: {}\n", encoding="utf-8")
    (job_dir / "pipeline.yaml").write_text("version: '1.0'\nstages: []\n", encoding="utf-8")

    loader = YamlConfigLoader(str(job_dir))

    with pytest.raises(ValueError):
        loader.load_job()
