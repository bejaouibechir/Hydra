# -*- coding: utf-8 -*-
"""
tests/test_fs_project_marker.py — le selecteur de dossier du Studio reconnait un
projet Hydra a son sous-dossier `.hydra`.

Les dossiers caches restent masques de la liste (`.hydra` n'apparait pas) ; c'est
le champ `is_project` qui porte l'information.
"""
from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi", reason="l'extra [server] n'est pas installe")

from hydra_etl.api import store  # noqa: E402
from hydra_etl.api.routers.fs import fs_list  # noqa: E402


def _make_project(path):
    (path / ".hydra").mkdir(parents=True)
    (path / ".hydra" / "project.json").write_text(
        json.dumps({"id": "abc12345", "name": path.name}), encoding="utf-8")


def test_marker_makes_a_project(tmp_path):
    proj = tmp_path / "mon-projet"
    _make_project(proj)
    assert store.is_hydra_project(proj) is True


def test_plain_folder_is_not_a_project(tmp_path):
    plain = tmp_path / "documents"
    plain.mkdir()
    (plain / "notes.txt").write_text("x", encoding="utf-8")
    assert store.is_hydra_project(plain) is False


def test_hydra_subfolder_is_enough(tmp_path):
    other = tmp_path / "autre"
    (other / ".hydra").mkdir(parents=True)
    assert store.is_hydra_project(other) is True


def test_structure_or_legacy_files_without_hydra_folder_is_not_a_project(tmp_path):
    structured = tmp_path / "structured"
    (structured / "workflows").mkdir(parents=True)
    (structured / "workflows" / "wf1.yaml").write_text("version: '1.0'", encoding="utf-8")
    (structured / "project.yaml").write_text("x: 1", encoding="utf-8")
    assert store.is_hydra_project(structured) is False


def test_fs_list_flags_projects_and_hides_the_marker_folder(tmp_path):
    _make_project(tmp_path / "projet-a")
    (tmp_path / "simple").mkdir()

    res = fs_list(path=str(tmp_path), dirs_only=True, ext="")
    by_name = {e["name"]: e for e in res["entries"]}

    assert by_name["projet-a"]["is_project"] is True
    assert by_name["simple"]["is_project"] is False
    assert ".hydra" not in by_name           # dossiers caches toujours masques
    assert res["is_project"] is False        # le dossier liste lui-meme n'est pas un projet


def test_fs_list_reports_when_the_listed_folder_is_a_project(tmp_path):
    proj = tmp_path / "p"
    _make_project(proj)
    (proj / "jobs").mkdir()
    res = fs_list(path=str(proj), dirs_only=True, ext="")
    assert res["is_project"] is True
