"""Studio et workflows/thread.yaml : lecture, écriture, vérification et
lancement d'un projet entier (comme `hdrctl run <projet>`)."""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

pytest.importorskip("fastapi", reason="l'extra [server] n'est pas installe")

from fastapi.testclient import TestClient  # noqa: E402
from click.testing import CliRunner  # noqa: E402

from hydra_etl.api import store  # noqa: E402
from hydra_etl.cli.hdrctl import cli  # noqa: E402
from hydra_etl.workflow.thread import load_thread  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "WORKSPACE", tmp_path / "ws")
    monkeypatch.setattr(store, "_INDEX_FILE", tmp_path / "ws" / "index.json")
    (tmp_path / "ws").mkdir()
    import hydra_etl.api.main as main
    return TestClient(main.app)


@pytest.fixture
def proj(tmp_path, client):
    root = tmp_path / "cli_proj"
    assert CliRunner().invoke(cli, ["init", str(root), "-q"]).exit_code == 0
    p = store.open_project(str(root))
    log = (root / "log.txt").as_posix()
    for name, code in (("a", "0"), ("b", "0"), ("boom", "3")):
        script = f"open(r'{log}', 'a').write('{name}' + chr(10)); import sys; sys.exit({code})"
        (root / "workflows" / f"{name}.yaml").write_text(textwrap.dedent(f"""\
            workflow:
              name: {name}
              steps:
                - name: s
                  type: action
                  action: python
                  params:
                    script: {json.dumps(script)}
            """), encoding="utf-8")
    return p, root


def test_get_thread(client, proj):
    p, root = proj
    r = client.get(f"/api/projects/{p.id}/thread")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["implicit"] is False
    assert d["workflows"] == ["a", "b", "boom", "workflow1"]
    assert [w["name"] for w in d["thread"]["thread"][0]["workflows"]] == ["workflow1"]
    assert d["missing"] == []


def test_put_thread_writes_file(client, proj):
    p, root = proj
    body = {"thread": [
        {"mode": "sequential", "delay_after": "1s", "workflows": [{"name": "a"}, {"name": "workflow1", "active": False}]},
        {"mode": "parallel", "workflows": [{"name": "b"}, {"name": "boom", "active": False}]},
    ]}
    r = client.put(f"/api/projects/{p.id}/thread", json=body)
    assert r.status_code == 200, r.text
    th = load_thread(root / "workflows" / "thread.yaml")
    assert [(s.mode, [(w.name, w.active) for w in s.workflows]) for s in th.thread] == [
        ("sequential", [("a", True), ("workflow1", False)]),
        ("parallel", [("b", True), ("boom", False)]),
    ]
    assert th.thread[0].delay_after == "1s"


@pytest.mark.parametrize("body,fragment", [
    ({"thread": [{"workflows": [{"name": "ghost"}]}]}, "ghost"),
    ({"thread": [{"mode": "random", "workflows": [{"name": "a"}]}]}, "mode"),
    ({"thread": [{"workflows": [{"name": "a"}]}, {"workflows": [{"name": "a"}]}]}, "more than once"),
])
def test_put_thread_rejects_invalid(client, proj, body, fragment):
    p, root = proj
    before = (root / "workflows" / "thread.yaml").read_text(encoding="utf-8")
    r = client.put(f"/api/projects/{p.id}/thread", json=body)
    assert r.status_code == 422 and fragment in r.text
    assert (root / "workflows" / "thread.yaml").read_text(encoding="utf-8") == before


def test_check(client, proj):
    p, root = proj
    r = client.post(f"/api/projects/{p.id}/check").json()
    assert r == {"ok": True, "errors": [], "active": ["workflow1"]}
    client.put(f"/api/projects/{p.id}/thread", json={"thread": [{"workflows": [{"name": "a"}]}]})
    (root / "workflows" / "a.yaml").write_text("workflow: {name: a, steps: nope}\n", encoding="utf-8")
    r = client.post(f"/api/projects/{p.id}/check").json()
    assert r["ok"] is False and "a.yaml" in r["errors"][0]


def test_run_project_from_studio(client, proj):
    p, root = proj
    client.put(f"/api/projects/{p.id}/thread", json={"thread": [
        {"workflows": [{"name": "a"}, {"name": "b", "active": False}, {"name": "boom"}, {"name": "workflow1"}]},
    ]})
    r = client.post("/api/runs", json={"workflow_path": str(root)})
    assert r.status_code == 202, r.text
    run = client.get(f"/api/runs/{r.json()['run_id']}").json()      # tâche de fond terminée
    assert run["workflow_name"] == "project:cli_proj"
    assert run["status"] == "failed" and "boom" in run["error"]
    got = [(s["step_name"], s["success"], s["skipped"]) for s in run["steps"]]
    assert got == [("a", True, False), ("b", True, True), ("boom", False, False), ("workflow1", True, True)]
    assert (root / "log.txt").read_text(encoding="utf-8").splitlines() == ["a", "boom"]


def test_run_project_success(client, proj):
    p, root = proj
    r = client.post("/api/runs", json={"workflow_path": str(root)})
    run = client.get(f"/api/runs/{r.json()['run_id']}").json()
    assert run["status"] == "success" and [s["step_name"] for s in run["steps"]] == ["workflow1"]


def test_put_and_get_loops(client, proj):
    p, root = proj
    body = {"thread": [{"workflows": [{"name": "a"}, {"name": "b"}]}],
            "loops": [{"from": "b", "to": "a", "times": 3, "delay": "1s"}]}
    r = client.put(f"/api/projects/{p.id}/thread", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["thread"]["loops"] == [{"from": "b", "to": "a", "times": 3, "delay": "1s"}]
    assert "loops:" in (root / "workflows" / "thread.yaml").read_text(encoding="utf-8")
    bad = {"thread": [{"workflows": [{"name": "a"}, {"name": "b"}]}], "loops": [{"from": "a", "to": "b", "times": 2}]}
    r = client.put(f"/api/projects/{p.id}/thread", json=bad)
    assert r.status_code == 422 and "must come before" in r.text


def test_run_project_with_loop_records_each_pass(client, proj):
    p, root = proj
    client.put(f"/api/projects/{p.id}/thread", json={
        "thread": [{"workflows": [{"name": "a"}, {"name": "b"}]}],
        "loops": [{"from": "b", "to": "a", "times": 2}]})
    r = client.post("/api/runs", json={"workflow_path": str(root)})
    run = client.get(f"/api/runs/{r.json()['run_id']}").json()
    assert run["status"] == "success"
    assert [s["step_name"] for s in run["steps"]] == ["a (pass 1/2)", "b (pass 1/2)", "a (pass 2/2)", "b (pass 2/2)"]
