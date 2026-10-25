"""Studio et fallback (étape 3) : aide aux conditions, vérification en direct,
thread.yaml avec fallback enregistré depuis Studio, avertissements de Check,
décision jointe aux steps d'un run de projet."""
from __future__ import annotations

import json
import textwrap
import time

import pytest

pytest.importorskip("fastapi", reason="l'extra [server] n'est pas installe")

from fastapi.testclient import TestClient  # noqa: E402
from click.testing import CliRunner  # noqa: E402

from hydra_etl.api import store  # noqa: E402
from hydra_etl.cli.hdrctl import cli  # noqa: E402
from hydra_etl.workflow.conditions import FUNCTION_HELP, FUNCTIONS  # noqa: E402
from hydra_etl.workflow.thread import load_thread  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("HYDRA_SECRETS_FILE", raising=False)   # laissé par d'autres tests
    monkeypatch.setattr(store, "WORKSPACE", tmp_path / "ws")
    monkeypatch.setattr(store, "_INDEX_FILE", tmp_path / "ws" / "index.json")
    (tmp_path / "ws").mkdir()
    import hydra_etl.api.main as main
    return TestClient(main.app)


@pytest.fixture
def proj(tmp_path, client):
    root = tmp_path / "p"
    assert CliRunner().invoke(cli, ["init", str(root), "-q"]).exit_code == 0
    (root / ".hydra" / "secrets").write_text("API_TOKEN=abc\n", encoding="utf-8")
    log = (root / "log.txt").as_posix()
    for name in ("a", "a_backup"):
        script = f"open(r'{log}', 'a').write('{name}' + chr(10))"
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
    return store.open_project(str(root)), root


def test_help_lists_every_function_and_declared_names(client, proj):
    p, _ = proj
    assert set(FUNCTION_HELP) == set(FUNCTIONS)
    d = client.get(f"/api/projects/{p.id}/conditions").json()
    assert [f["name"] for f in d["functions"]] == list(FUNCTIONS)
    sa = next(f for f in d["functions"] if f["name"] == "source_available")
    assert sa["arg"] == "source" and sa["returns"] == "bool"
    assert set(d["attributes"]) == {"previous.status", "previous.rows"}
    assert d["sources"] == ["src_csv"] and d["destinations"] == ["dest_csv"]
    assert d["secrets"] == ["API_TOKEN"]
    assert "abc" not in json.dumps(d)                     # jamais les valeurs


def test_live_condition_check(client, proj):
    p, _ = proj
    ok = lambda w: client.post(f"/api/projects/{p.id}/conditions/check", json={"when": w}).json()  # noqa: E731
    assert ok("not source_available('src_csv') or file_age('in.csv') > 24h") == {"ok": True, "error": None}
    r = ok("source_available('nope')")
    assert not r["ok"] and "'nope' is not declared" in r["error"]
    r = ok("__import__('os')")
    assert not r["ok"] and "unknown function __import__()" in r["error"]
    assert not ok("file_exists('x') and")["ok"]
    assert "reserved" in ok("estimate.duration > 30m")["error"]


def test_save_fallback_from_studio_then_check_and_run(client, proj):
    p, root = proj
    body = {"thread": [{"mode": "sequential", "workflows": [
        {"name": "workflow1", "active": True},
        {"name": "a", "active": True,
         "fallback": {"use": ["a_backup"], "when": "file_exists('flag')"}},
    ]}], "loops": []}
    r = client.put(f"/api/projects/{p.id}/thread", json=body)
    assert r.status_code == 200, r.text
    w = r.json()["thread"]["thread"][0]["workflows"][1]
    assert w["fallback"]["use"] == ["a_backup"] and w["fallback"]["when"] == "file_exists('flag')"
    th = load_thread(root / "workflows" / "thread.yaml")
    assert th.fallback_names() == ["a_backup"]

    # condition invalide refusée à l'enregistrement
    bad = json.loads(json.dumps(body))
    bad["thread"][0]["workflows"][1]["fallback"]["when"] = "open('x')"
    assert client.put(f"/api/projects/{p.id}/thread", json=bad).status_code == 422
    # remplaçant aussi dans le thread : refusé
    bad = json.loads(json.dumps(body))
    bad["thread"][0]["workflows"].append({"name": "a_backup", "active": True})
    assert client.put(f"/api/projects/{p.id}/thread", json=bad).status_code == 422

    c = client.post(f"/api/projects/{p.id}/check").json()
    assert c["ok"] and c["active"] == ["workflow1", "a"]
    # a et a_backup n'écrivent rien : mêmes destinations, pas d'avertissement
    assert c["warnings"] == []

    def run_project():
        rid = client.post("/api/runs", json={"workflow_path": str(root)}).json()["run_id"]
        for _ in range(150):
            run_ = client.get(f"/api/runs/{rid}").json()
            if run_["status"] in ("success", "failed"):
                return run_
            time.sleep(0.1)
        raise AssertionError("run did not finish")

    run_ = run_project()
    assert run_["status"] == "success", run_
    step = run_["steps"][1]
    assert step["step_name"] == "a"
    assert step["fallback"] == {"workflow": "a", "action": "kept", "use": "a_backup",
                                "trigger": None, "reason": "file_exists('flag') = false (not found)"}
    assert "fallback" not in run_["steps"][0]

    (root / "flag").write_text("x")
    step = run_project()["steps"][1]
    assert step["step_name"] == "a_backup — fallback of a"
    assert step["fallback"]["action"] == "switched" and step["fallback"]["trigger"] == "when"
    assert step["fallback"]["reason"] == "file_exists('flag') = true"


def test_check_warns_on_different_destinations(client, proj):
    p, root = proj
    (root / "workflows" / "a.yaml").write_text(textwrap.dedent("""\
        workflow:
          name: a
          steps:
            - name: s
              type: job
              job: ../jobs/job1
        """), encoding="utf-8")
    client.put(f"/api/projects/{p.id}/thread", json={"thread": [{"mode": "sequential", "workflows": [
        {"name": "a", "active": True, "fallback": {"use": ["a_backup"], "on_failure": True}}]}]})
    c = client.post(f"/api/projects/{p.id}/check").json()
    assert c["ok"], c
    assert len(c["warnings"]) == 1 and "'a_backup' writes to nothing" in c["warnings"][0]
