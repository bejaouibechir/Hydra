"""Studio : un workflows/*.yaml sans méta Studio (créé par hdrctl, arrivé par git, méta
effacée) apparaît dans la liste du projet déjà ouvert, sans que le YAML change."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi", reason="l'extra [server] n'est pas installe")

from hydra_etl.api import store  # noqa: E402

WF = ('version: "1.0"\nworkflow:\n  name: sync\n  description: Mirror the orders   # why\n'
      '  steps:\n    - name: orders\n      type: job\n      job: ../jobs/orders\n')


@pytest.fixture
def cloned(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "WORKSPACE", tmp_path / "ws")
    monkeypatch.setattr(store, "_INDEX_FILE", tmp_path / "ws" / "index.json")
    (tmp_path / "ws").mkdir()
    root = tmp_path / "demo"
    (root / "workflows").mkdir(parents=True)
    (root / "jobs" / "orders").mkdir(parents=True)
    (root / "workflows" / "sync.yaml").write_text(WF, encoding="utf-8")
    (root / "workflows" / "thread.yaml").write_text(
        'version: "1.0"\nthread:\n  - mode: sequential\n    workflows:\n      - name: sync\n', encoding="utf-8")
    (root / "workflows" / "notes.yaml").write_text("just: notes\n", encoding="utf-8")
    (root / ".hydra").mkdir()
    (root / ".hydra" / "project.json").write_text(
        '{"id": "abc", "name": "demo", "workflows": [], "jobs": []}\n', encoding="utf-8")
    proj = store.open_project(str(root))
    manifest = (root / ".hydra" / "project.json").read_text(encoding="utf-8")
    return proj, root, manifest


def test_orphan_workflow_is_listed_once_without_touching_files(cloned):
    proj, root, _ = cloned
    import shutil
    shutil.rmtree(root / ".hydra" / "workflows", ignore_errors=True)   # méta effacée, projet ouvert
    wfs = store.list_workflows(proj.id)
    assert [w.name for w in wfs] == ["sync"]                 # thread.yaml et notes.yaml ignorés
    assert wfs[0].description == "Mirror the orders"
    assert [w.id for w in store.list_workflows(proj.id)] == [wfs[0].id]   # pas de doublon
    assert (root / "workflows" / "sync.yaml").read_text(encoding="utf-8") == WF


def test_adopted_workflow_opens_without_conflict(cloned):
    proj, root, _ = cloned
    wf = store.list_workflows(proj.id)[0]
    got = store.get_workflow(proj.id, wf.id)
    assert got.yaml_content == WF
    assert got.external_changes is None
    assert "workflows/sync.yaml" in got.disk_state
