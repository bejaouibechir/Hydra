"""Ordre des cartes de workflows sur la page projet de Studio (glisser-déposer).

Purement visuel : rangé dans .hydra/project.json ("card_order"), sans effet
sur workflows/thread.yaml.
"""
import json

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from hydra_etl.api import store
from hydra_etl.cli.hdrctl import cli


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "WORKSPACE", tmp_path / "ws")
    monkeypatch.setattr(store, "_INDEX_FILE", tmp_path / "ws" / "index.json")
    (tmp_path / "ws").mkdir()
    import hydra_etl.api.main as main
    return TestClient(main.app)


@pytest.fixture
def proj(tmp_path, client):
    root = tmp_path / "p"
    assert CliRunner().invoke(cli, ["init", str(root), "-q"]).exit_code == 0
    p = store.open_project(str(root))
    ids = []
    for name in ("alpha", "beta", "gamma"):
        r = client.post("/api/workflows", json={"name": name, "project_id": p.id})
        assert r.status_code in (200, 201), r.text
        ids.append(r.json()["id"])
    return p, root, ids


def names(client, pid):
    return [w["name"] for w in client.get(f"/api/workflows?project_id={pid}").json()]


def test_reorder_is_kept(client, proj):
    p, root, (a, b, g) = proj
    before = names(client, p.id)
    thread_before = (root / "workflows" / "thread.yaml").read_text(encoding="utf-8")
    r = client.put(f"/api/projects/{p.id}/card-order", json={"order": [g, a]})
    assert r.status_code == 200, r.text
    order = r.json()["order"]
    assert order[:2] == [g, a] and set(order) >= {a, b, g}
    after = names(client, p.id)
    assert after[:2] == ["gamma", "alpha"]
    assert sorted(after) == sorted(before)
    meta = json.loads((root / ".hydra" / "project.json").read_text(encoding="utf-8"))
    assert meta["card_order"] == order
    # visuel seulement
    assert (root / "workflows" / "thread.yaml").read_text(encoding="utf-8") == thread_before


def test_unknown_and_duplicate_ids_ignored(client, proj):
    p, _, (a, b, g) = proj
    r = client.put(f"/api/projects/{p.id}/card-order", json={"order": ["nope", b, b, a]})
    assert r.status_code == 200
    order = r.json()["order"]
    assert order[:2] == [b, a] and "nope" not in order and order.count(b) == 1


def test_new_workflow_goes_last_and_deleted_leaves_order(client, proj):
    p, _, (a, b, g) = proj
    client.put(f"/api/projects/{p.id}/card-order", json={"order": [g, b, a]})
    r = client.post("/api/workflows", json={"name": "delta", "project_id": p.id})
    assert names(client, p.id)[-1] == "delta"
    assert client.delete(f"/api/workflows/{b}?project_id={p.id}").status_code == 200
    meta = json.loads((store._resolve_project_path(p.id) / ".hydra" / "project.json").read_text(encoding="utf-8"))
    assert b not in meta["card_order"]
    assert names(client, p.id)[:2] == ["gamma", "alpha"]


def test_unknown_project_404(client):
    assert client.put("/api/projects/zzz/card-order", json={"order": []}).status_code == 404
