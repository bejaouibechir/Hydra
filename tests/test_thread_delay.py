"""delay_before : attente avant le lancement d'un workflow du thread
(séquentiel : après le précédent ; parallèle : départs décalés)."""
from __future__ import annotations

import json
import textwrap
import time
from pathlib import Path

import pytest
from click.testing import CliRunner

from hydra_etl.cli.hdrctl import cli
from hydra_etl.workflow.project import (
    FAILED, NOT_RUN, SUCCESS, ProjectRunner, prepare_project,
)
from hydra_etl.workflow.thread import parse_thread, render_thread


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "proj"
    assert CliRunner().invoke(cli, ["init", str(r), "-q"]).exit_code == 0
    return r


def wf(root: Path, name: str, code: str = "") -> None:
    log = (root / "log.txt").as_posix()
    script = f"import time; open(r'{log}', 'a').write('{name} %.3f\\n' % time.time()){code}"
    (root / "workflows" / f"{name}.yaml").write_text(textwrap.dedent(f"""\
        version: "1.0"
        workflow:
          name: {name}
          steps:
            - name: act
              type: action
              action: python
              params:
                script: {json.dumps(script)}
        """), encoding="utf-8")


def thread(root: Path, body: str) -> None:
    (root / "workflows" / "thread.yaml").write_text(
        'version: "1.0"\nthread:\n' + textwrap.dedent(body), encoding="utf-8")


def starts(root: Path) -> dict:
    f = root / "log.txt"
    out = {}
    for line in (f.read_text(encoding="utf-8").splitlines() if f.exists() else []):
        n, ts = line.split()
        out[n] = float(ts)
    return out


def run(root: Path, **kw):
    events = []
    res = ProjectRunner(prepare_project(root), **kw).run(lambda k, d: events.append((k, d)))
    return res, events


def test_model_validates_and_renders():
    th = parse_thread({"version": "1.0", "thread": [{"mode": "parallel", "workflows": [
        {"name": "a", "delay_before": "500ms"}, {"name": "b", "delay_before": 2}, {"name": "c"}]}]})
    ws = th.thread[0].workflows
    assert [w.delay_before_seconds for w in ws] == [0.5, 2.0, 0.0]
    text = render_thread(th)
    assert "delay_before: 500ms" in text and "delay_before: 2\n" in text
    assert parse_thread(__import__("yaml").safe_load(text)).thread[0].workflows[0].delay_before == "500ms"
    with pytest.raises(ValueError):
        parse_thread({"thread": [{"workflows": [{"name": "a", "delay_before": "soon"}]}]})


def test_sequential_waits_before_each_workflow(root):
    wf(root, "a"); wf(root, "b")
    thread(root, """\
        - mode: sequential
          workflows:
            - name: a
              delay_before: 7s
            - name: b
              delay_before: 3m
        """)
    slept = []
    res, ev = run(root, sleep=slept.append)
    assert res.success and slept == [7.0, 180.0]
    waits = [d for k, d in ev if k == "wait"]
    assert [(w["name"], w["seconds"], w["parallel"]) for w in waits] == [("a", 7.0, False), ("b", 180.0, False)]
    # l'attente précède le départ du workflow
    order = [k if k != "start" else f"start {d['name']}" for k, d in ev if k in ("wait", "start")]
    assert order == ["wait", "start a", "wait", "start b"]


def test_parallel_starts_are_staggered(root):
    for n in ("fast", "slow"):
        wf(root, n)
    thread(root, """\
        - mode: parallel
          workflows:
            - name: fast
            - name: slow
              delay_before: 1.2
        """)
    t0 = time.time()
    res, _ = run(root)
    s = starts(root)
    assert res.success
    assert s["slow"] - s["fast"] >= 1.0 and time.time() - t0 < 6


def test_parallel_failure_cancels_waiting_starts(root):
    wf(root, "boom", "; import sys; sys.exit(3)")
    wf(root, "later")
    thread(root, """\
        - mode: parallel
          workflows:
            - name: boom
            - name: later
              delay_before: 20s
        """)
    t0 = time.time()
    res, ev = run(root)
    assert time.time() - t0 < 10                       # l'attente est interrompue
    by = {r.name: r for r in res.runs}
    assert by["boom"].status == FAILED and by["later"].status == NOT_RUN
    assert "another workflow of the stage failed" in by["later"].error
    assert "later" not in starts(root)


def test_fallback_is_checked_after_the_wait(root):
    flag = (root / "flag").as_posix()
    wf(root, "maker", f"; open(r'{flag}', 'w').write('x')")
    wf(root, "late"); wf(root, "late_alt")
    thread(root, """\
        - mode: parallel
          workflows:
            - name: maker
            - name: late
              delay_before: 1s
              fallback:
                use: [late_alt]
                when: "file_exists('flag')"
        """)
    res, _ = run(root)
    assert res.success
    assert [r.name for r in res.runs if r.status == SUCCESS] == ["maker", "late_alt"]


def test_inactive_workflow_does_not_wait(root):
    wf(root, "a")
    thread(root, """\
        - mode: sequential
          workflows:
            - name: a
              active: false
              delay_before: 1h
        """)
    slept = []
    res, ev = run(root, sleep=slept.append)
    assert slept == [] and not [k for k, _ in ev if k == "wait"]


def test_cli_plan_and_run_show_the_wait(root):
    wf(root, "a"); wf(root, "b")
    thread(root, """\
        - mode: parallel
          workflows:
            - name: a
            - name: b
              delay_before: 0.3s
        """)
    r = CliRunner().invoke(cli, ["run", str(root), "--dry-run", "--lang", "en"])
    assert r.exit_code == 0 and "waits 0.3s before starting (after the stage starts)" in r.output
    r = CliRunner().invoke(cli, ["run", str(root), "--lang", "en"])
    assert r.exit_code == 0 and "b: waiting 0.3s before starting" in r.output


def test_studio_run_logs_the_wait(root, tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from hydra_etl.api import store
    monkeypatch.setattr(store, "WORKSPACE", tmp_path / "ws")
    monkeypatch.setattr(store, "_INDEX_FILE", tmp_path / "ws" / "index.json")
    (tmp_path / "ws").mkdir()
    import hydra_etl.api.main as main
    client = TestClient(main.app)
    wf(root, "a")
    thread(root, """\
        - mode: sequential
          workflows:
            - name: a
              delay_before: 0.2s
        """)
    store.open_project(str(root))
    rid = client.post("/api/runs", json={"workflow_path": str(root)}).json()["run_id"]
    for _ in range(100):
        run_ = client.get(f"/api/runs/{rid}").json()
        if run_["status"] in ("success", "failed"):
            break
        time.sleep(0.1)
    assert run_["status"] == "success"
    assert run_["steps"][0]["logs"][0] == "waited 0.2s before starting (delay_before)"
    assert run_["steps"][0]["waited"] == 0.2
