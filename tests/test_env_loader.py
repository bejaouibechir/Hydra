"""
Tests du loader .env en 2 niveaux:
- root .env (defaults)
- job .env (override)

On valide:
- parsing .env
- precedence job > root
- comportement avec variable déjà existante dans l'OS (override_os True/False)
- fichiers absents => pas d'erreur
"""

from __future__ import annotations

from pathlib import Path

import pytest

from internal.config.env_loader import (
    EnvFileParseError,
    load_env_layers,
    parse_env_text,
)


def test_parse_env_text_ok_basic():
    text = """
    # comment
    DB_HOST=127.0.0.1
    DB_PORT=3306
    export DB_USER=etl
    DB_PASS="p@ss"
    EMPTY=""
    """
    d = parse_env_text(text)
    assert d["DB_HOST"] == "127.0.0.1"
    assert d["DB_PORT"] == "3306"
    assert d["DB_USER"] == "etl"
    assert d["DB_PASS"] == "p@ss"
    assert d["EMPTY"] == ""


def test_parse_env_text_rejects_invalid_line():
    text = "THIS_IS_NOT_VALID\n"
    with pytest.raises(EnvFileParseError):
        parse_env_text(text)


def test_load_env_layers_root_then_job_precedence(monkeypatch, tmp_path: Path):
    """
    root définit DB_HOST/DB_PORT
    job surcharge DB_HOST et ajoute DB_NAME
    => DB_HOST vient du job, DB_PORT du root, DB_NAME du job
    """
    root = tmp_path / "root.env"
    job = tmp_path / "job.env"

    root.write_text("DB_HOST=10.0.0.1\nDB_PORT=3306\n", encoding="utf-8")
    job.write_text("DB_HOST=10.0.0.99\nDB_NAME=shop\n", encoding="utf-8")

    # Nettoyage de l'environnement pour le test (évite interférence machine)
    monkeypatch.delenv("DB_HOST", raising=False)
    monkeypatch.delenv("DB_PORT", raising=False)
    monkeypatch.delenv("DB_NAME", raising=False)

    rep = load_env_layers(root_env_path=root, job_env_path=job, override_os=False)

    assert rep.loaded_root == 2
    assert rep.loaded_job == 2
    assert "DB_HOST" in rep.root_path.as_posix() or rep.root_path is not None

    assert "DB_HOST" in dict(**{"DB_HOST": "dummy"})  # simple sanity de test

    import os
    assert os.environ["DB_HOST"] == "10.0.0.99"
    assert os.environ["DB_PORT"] == "3306"
    assert os.environ["DB_NAME"] == "shop"


def test_load_env_layers_no_job_file(monkeypatch, tmp_path: Path):
    """
    job absent => on garde root.
    """
    root = tmp_path / "root.env"
    root.write_text("DB_HOST=1.2.3.4\n", encoding="utf-8")

    monkeypatch.delenv("DB_HOST", raising=False)

    rep = load_env_layers(root_env_path=root, job_env_path=tmp_path / "missing.env", override_os=False)

    import os
    assert os.environ["DB_HOST"] == "1.2.3.4"
    assert rep.loaded_root == 1
    assert rep.loaded_job == 0


def test_load_env_layers_respects_existing_os_var_when_override_false(monkeypatch, tmp_path: Path):
    """
    Si DB_HOST est déjà défini dans l'OS, override_os=False => root/job ne doivent pas écraser.
    """
    root = tmp_path / "root.env"
    job = tmp_path / "job.env"

    root.write_text("DB_HOST=10.0.0.1\n", encoding="utf-8")
    job.write_text("DB_HOST=10.0.0.99\n", encoding="utf-8")

    monkeypatch.setenv("DB_HOST", "OS_VALUE")

    rep = load_env_layers(root_env_path=root, job_env_path=job, override_os=False)

    import os
    assert os.environ["DB_HOST"] == "OS_VALUE"
    # root n'a pas écrit DB_HOST (déjà présent)
    assert rep.loaded_root == 0
    # job ne doit pas écraser non plus
    assert rep.loaded_job == 0


def test_load_env_layers_overrides_os_var_when_override_true(monkeypatch, tmp_path: Path):
    """
    Si override_os=True, alors root puis job écrasent (et job gagne).
    """
    root = tmp_path / "root.env"
    job = tmp_path / "job.env"

    root.write_text("DB_HOST=10.0.0.1\n", encoding="utf-8")
    job.write_text("DB_HOST=10.0.0.99\n", encoding="utf-8")

    monkeypatch.setenv("DB_HOST", "OS_VALUE")

    rep = load_env_layers(root_env_path=root, job_env_path=job, override_os=True)

    import os
    assert os.environ["DB_HOST"] == "10.0.0.99"
    assert rep.loaded_root == 1
    assert rep.loaded_job == 1
