"""Webhook de projet, hdrctl trigger token, API des déclencheurs, moteur dans serve (0.19, lot 2.5)."""
import json
import os
import time
from pathlib import Path

import pytest
from click.testing import CliRunner

fastapi = pytest.importorskip("fastapi", reason="l'extra [server] n'est pas installe")
from fastapi.testclient import TestClient  # noqa: E402

from hydra_etl.api import store, trigger_service  # noqa: E402
from hydra_etl.cli.hdrctl import cli  # noqa: E402
from hydra_etl.triggers.core import read_history  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
TRIGGERS = ("triggers:\n"
            "  - {name: on_push, type: webhook, token: '${SECRET:trigger.on_push.token}'}\n"
            "  - {name: nightly, type: cron, cron: '0 2 * * *'}\n"
            "  - {name: paused, type: interval, every: 1m, enabled: false}\n")


def _project(base: Path) -> Path:
    root = base / "p"
    (root / ".hydra").mkdir(parents=True)
    (root / ".hydra" / "project.json").write_text(json.dumps({"id": "p0", "name": "p"}))
    (root / "workflows").mkdir()
    (root / "workflows" / "main.yaml").write_text(
        "workflow:\n  name: main\n  steps:\n    - name: s\n      type: action\n      action: python\n"
        "      params:\n        script: 'print(\"hooked\")'\n")
    (root / "workflows" / "thread.yaml").write_text(
        "thread:\n  - mode: sequential\n    workflows:\n      - name: main\n")
    (root / "triggers.yaml").write_text(TRIGGERS)
    return root


# ── hdrctl trigger token ──────────────────────────────────────────────────

def _token(out: str) -> str:
    lines = [l.strip() for l in out.splitlines()]
    i = next(i for i, l in enumerate(lines) if "not shown again" in l)
    return next(l for l in lines[i + 1:] if l)


def test_token_saved_once_then_rotated(tmp_path):
    root = _project(tmp_path)
    r = CliRunner()
    out = r.invoke(cli, ["trigger", "token", "on_push", "--project", str(root)])
    assert out.exit_code == 0, out.output
    tok = _token(out.output)
    assert len(tok) >= 40
    assert f"trigger.on_push.token={tok}" in (root / ".hydra" / "secrets").read_text()
    assert "/api/projects/p0/triggers/on_push/webhook" in out.output
    again = r.invoke(cli, ["trigger", "token", "on_push", "--project", str(root)])
    assert again.exit_code == 1 and "already set" in again.output
    rot = r.invoke(cli, ["trigger", "token", "on_push", "--project", str(root), "--rotate"])
    assert rot.exit_code == 0 and _token(rot.output) != tok


def test_token_per_environment_and_wrong_trigger(tmp_path):
    root = _project(tmp_path)
    r = CliRunner()
    out = r.invoke(cli, ["trigger", "token", "on_push", "--project", str(root), "--env", "prod"])
    assert out.exit_code == 0
    assert (root / ".hydra" / "secrets.prod").exists()
    bad = r.invoke(cli, ["trigger", "token", "nightly", "--project", str(root)])
    assert bad.exit_code == 1 and "not a webhook" in bad.output and "on_push" in bad.output


# ── API ───────────────────────────────────────────────────────────────────

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "WORKSPACE", tmp_path / "ws")
    monkeypatch.setattr(store, "_INDEX_FILE", tmp_path / "ws" / "index.json")
    monkeypatch.setattr(store, "_HIDDEN_FILE", tmp_path / "ws" / "hidden.json", raising=False)
    (tmp_path / "ws").mkdir()
    monkeypatch.setenv("PYTHONPATH", str(REPO) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    from hydra_etl.api.main import app
    trigger_service.shutdown(0)
    with TestClient(app) as c:
        yield c
    trigger_service.shutdown(30)


@pytest.fixture
def proj(tmp_path, client):
    root = _project(tmp_path)
    p = store.open_project(str(root))
    trigger_service.sync()
    return p, root


def _wait_history(root, n=1, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        h = read_history(root)
        if len(h) >= n:
            return h
        time.sleep(0.2)
    return read_history(root)


def test_list_triggers(client, proj):
    p, root = proj
    data = client.get(f"/api/projects/{p.id}/triggers").json()
    by = {t["name"]: t for t in data["triggers"]}
    assert by["nightly"]["next"] and by["nightly"]["type"] == "cron"
    assert by["paused"]["note"].startswith("disabled")
    assert by["on_push"]["webhook"] == f"/api/projects/{p.id}/triggers/on_push/webhook"
    assert any("trigger.on_push.token" in w for w in data["warnings"])


def test_webhook_token_checks(client, proj):
    p, root = proj
    url = f"/api/projects/{p.id}/triggers/on_push/webhook"
    assert client.post(url).status_code == 503 or client.post(url).status_code == 401
    r = CliRunner().invoke(cli, ["trigger", "token", "on_push", "--project", str(root)])
    tok = _token(r.output)
    assert client.post(url).status_code == 401
    assert client.post(url, headers={"X-Hydra-Token": "wrong"}).status_code == 401
    assert client.post(f"/api/projects/{p.id}/triggers/nightly/webhook",
                       headers={"X-Hydra-Token": tok}).status_code == 404       # pas un webhook
    ok = client.post(url, headers={"Authorization": f"Bearer {tok}"})
    assert ok.status_code == 202 and ok.json()["origin"] == "webhook"
    h = _wait_history(root)
    assert h[-1]["trigger"] == "on_push" and h[-1]["origin"] == "webhook" and h[-1]["status"] == "success"


def test_fire_from_api(client, proj):
    p, root = proj
    r = client.post(f"/api/projects/{p.id}/triggers/nightly/fire")
    assert r.status_code == 202
    assert client.post(f"/api/projects/{p.id}/triggers/nightly/fire").status_code in (202, 409)
    assert client.post(f"/api/projects/{p.id}/triggers/paused/fire").status_code == 202   # à la main : oui
    assert client.post(f"/api/projects/{p.id}/triggers/ghost/fire").status_code == 404
    h = _wait_history(root, n=2)
    assert {e["trigger"] for e in h} >= {"nightly", "paused"} and h[0]["origin"] == "api"
    hist = client.get(f"/api/projects/{p.id}/triggers/history?name=nightly").json()
    assert hist and hist[0]["trigger"] == "nightly"


def test_serve_follows_the_project_list(client, proj):
    p, root = proj
    eng = trigger_service.engine()
    assert root.resolve() in eng.projects
    client.post(f"/api/projects/{p.id}/unlist")
    assert root.resolve() not in eng.projects


# ── Studio : enregistrer triggers.yaml, créer le jeton (étape 3) ──────────────

def test_save_triggers_roundtrip(client, proj):
    p, root = proj
    data = client.get(f"/api/projects/{p.id}/triggers").json()
    configs = [t["config"] for t in data["triggers"]]
    assert configs[0]["name"] == "on_push" and "enabled" not in configs[0]
    configs.append({"name": "drop", "type": "file", "path": "inbox/*.csv", "events": ["added"],
                    "workflows": ["main"]})
    configs.append({"name": "after", "type": "after_project", "project": ".", "on": "any"})
    bad = client.put(f"/api/projects/{p.id}/triggers", json={"triggers": configs})
    assert bad.status_code == 422 and "own end" in str(bad.json())    # refusé : rien d'écrit
    assert "drop" not in (root / "triggers.yaml").read_text()
    configs.pop()
    r = client.put(f"/api/projects/{p.id}/triggers", json={"triggers": configs})
    assert r.status_code == 200, r.text
    assert [t["name"] for t in r.json()["triggers"]] == ["on_push", "nightly", "paused", "drop"]
    text = (root / "triggers.yaml").read_text()
    assert "Written by Hydra Studio" in text and "path: inbox/*.csv" in text
    from hydra_etl.triggers.models import load_triggers
    assert load_triggers(root).get("drop").workflows == ["main"]


def test_save_refuses_invalid_trigger(client, proj):
    p, root = proj
    r = client.put(f"/api/projects/{p.id}/triggers",
                   json={"triggers": [{"name": "x", "type": "cron"}]})
    assert r.status_code == 422 and "requires 'cron'" in str(r.json())
    r = client.put(f"/api/projects/{p.id}/triggers", json={"triggers": []})
    assert r.status_code == 200 and r.json()["triggers"] == []
    assert "triggers: []" in (root / "triggers.yaml").read_text()


def test_create_token_once(client, proj):
    p, root = proj
    url = f"/api/projects/{p.id}/triggers/on_push/token"
    r = client.post(url, json={})
    assert r.status_code == 200
    tok = r.json()["token"]
    assert r.json()["secret"] == "trigger.on_push.token" and len(tok) >= 40
    assert client.post(url, json={}).status_code == 409
    listed = client.get(f"/api/projects/{p.id}/triggers").json()
    hook = next(t for t in listed["triggers"] if t["name"] == "on_push")
    assert hook["token_set"] is True and tok not in str(listed)
    assert client.post(f"/api/projects/{p.id}/triggers/nightly/token", json={}).status_code == 404
    new = client.post(url, json={"rotate": True}).json()["token"]
    assert new != tok
    ok = client.post(f"/api/projects/{p.id}/triggers/on_push/webhook", headers={"X-Hydra-Token": new})
    assert ok.status_code == 202
    _wait_history(root)
