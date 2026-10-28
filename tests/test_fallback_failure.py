"""Fallback — étape 5b : bascule après un échec (`on_failure: true`) et
`timeout` par workflow. Le remplaçant ne part que si le workflow raté n'a rien
laissé de publié (rien chargé / rien fait dehors, ou tout défait par rollback)."""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
from click.testing import CliRunner

from hydra_etl.cli.hdrctl import cli
from hydra_etl.internal.runner.executor import JobExecutor
from hydra_etl.workflow.project import (
    FAILED, RECOVERED, SUCCESS, ProjectRunner, WorkflowRun, prepare_project, published_by,
)
from hydra_etl.workflow.stop import StopSignal
from hydra_etl.workflow.thread import ThreadDef, load_thread, render_thread


# ── Projet de test ──────────────────────────────────────────────────────────

def job(root: Path, name: str, out: str, mode: str = "replace", src: str = "in.csv") -> None:
    d = root / "jobs" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "sources.yaml").write_text(textwrap.dedent(f"""\
        sources:
          src:
            type: csv
            extract:
              table: ../../data/{src}
        """), encoding="utf-8")
    (d / "destinations.yaml").write_text(textwrap.dedent(f"""\
        destinations:
          dst:
            type: csv
            load:
              table: ../../data/{out}
              mode: {mode}
        """), encoding="utf-8")
    (d / "pipeline.yaml").write_text("pipeline:\n  from: src\n  to: dst\n", encoding="utf-8")


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "p"
    (r / ".hydra").mkdir(parents=True)
    (r / "workflows").mkdir()
    data = r / "data"
    data.mkdir()
    (data / "in.csv").write_text("id,v\n1,a\n2,b\n", encoding="utf-8")
    (data / "out1.csv").write_text("id,v\nold,1\n", encoding="utf-8")
    job(r, "j1", "out1.csv")
    job(r, "broken", "out3.csv", src="missing.csv")
    return r


def py(root: Path, name: str, code: str = "") -> str:
    """Action python qui note son passage dans log.txt, puis exécute `code`."""
    log = (root / "log.txt").as_posix()
    return json.dumps(f"open(r'{log}', 'a').write('{name}\\n')\n{code}")


def wf(root: Path, name: str, steps: str, rollback: bool = False) -> None:
    (root / "workflows" / f"{name}.yaml").write_text(
        f"workflow:\n  name: {name}\n" + ("  rollback: true\n" if rollback else "")
        + "  steps:\n" + textwrap.indent(textwrap.dedent(steps), "    "), encoding="utf-8")


def act(root: Path, name: str, code: str = "", step: str = "act") -> str:
    return f"""\
        - name: {step}
          type: action
          action: python
          params:
            script: {py(root, name, code)}
          undo: none
        """


FAIL = "raise RuntimeError('boom')"


def thread(root: Path, body: str) -> None:
    (root / "workflows" / "thread.yaml").write_text(
        'version: "1.0"\nthread:\n' + textwrap.dedent(body), encoding="utf-8")


def log(root: Path) -> list:
    f = root / "log.txt"
    return f.read_text(encoding="utf-8").split() if f.exists() else []


def run(root: Path, **kw):
    events = []
    result = ProjectRunner(prepare_project(root), **kw).run(lambda k, d: events.append((k, d)))
    return result, events


def kinds(events, kind):
    return [d for k, d in events if k == kind]


def one_slot(root: Path, fallback: str, extra: str = "") -> None:
    """main (avec `extra` puis le bloc fallback), puis after, dans une étape séquentielle.
    `fallback` : lignes du bloc, indentées de 10 espaces ; `extra` : de 8."""
    (root / "workflows" / "thread.yaml").write_text(
        'version: "1.0"\nthread:\n'
        "  - mode: sequential\n"
        "    workflows:\n"
        "      - name: main\n"
        + extra
        + "        fallback:\n"
        + fallback + "\n"
        "      - name: after\n", encoding="utf-8")


# ── Bascule après un échec ──────────────────────────────────────────────────

def test_failure_without_publication_switches_to_backup(root):
    wf(root, "main", act(root, "main", FAIL))
    wf(root, "backup", act(root, "backup"))
    wf(root, "after", act(root, "after"))
    one_slot(root, "          use: [backup]\n          on_failure: true")
    res, ev = run(root)
    assert res.success
    assert log(root) == ["main", "backup", "after"]
    assert [(r.name, r.status) for r in res.runs] == [
        ("main", RECOVERED), ("backup", SUCCESS), ("after", SUCCESS)]
    assert res.runs[0].replaced_by == "backup" and res.runs[1].replaces == "main"
    fb = kinds(ev, "fallback")
    assert len(fb) == 1 and fb[0]["trigger"] == "failure"
    assert "main failed without publishing anything" in fb[0]["reason"] and "boom" in fb[0]["reason"]


def test_no_switch_without_on_failure(root):
    wf(root, "main", act(root, "main", FAIL))
    wf(root, "backup", act(root, "backup"))
    wf(root, "after", act(root, "after"))
    one_slot(root, '          use: [backup]\n          when: "file_exists(\'nope.txt\')"')
    res, ev = run(root)
    assert not res.success and log(root) == ["main"]
    assert [r.status for r in res.runs][:1] == [FAILED]
    assert not kinds(ev, "fallback")


def test_published_data_blocks_the_switch(root):
    # load1 a publié out1.csv, puis le job suivant échoue : sans rollback, la
    # bascule doublerait les données → arrêt avec la raison.
    wf(root, "main", """\
        - name: load1
          type: job
          job: ../jobs/j1
        - name: last
          type: job
          job: ../jobs/broken
          depends_on: [load1]
        """)
    wf(root, "backup", act(root, "backup"))
    wf(root, "after", act(root, "after"))
    one_slot(root, "          use: [backup]\n          on_failure: true")
    res, ev = run(root)
    assert not res.success and log(root) == []
    main = res.runs[0]
    assert main.status == FAILED
    assert "fallback 'backup' not started: step 'load1' had already published its data" in main.error
    blocked = kinds(ev, "fallback_blocked")
    assert blocked and blocked[0]["use"] == "backup"
    # le message CLI dit pourquoi
    out = CliRunner().invoke(cli, ["run", str(root)]).output
    assert "fallback backup not started" in out and "already published" in out


def test_external_action_blocks_the_switch_unless_undo_none(root):
    def main(undo: str) -> None:
        wf(root, "main", f"""\
            - name: send
              type: action
              action: python
              params:
                script: {py(root, "send")}
            {undo}
            - name: fail
              type: action
              action: python
              params:
                script: {py(root, "fail", FAIL)}
              depends_on: [send]
            """)
    main("")
    wf(root, "backup", act(root, "backup"))
    wf(root, "after", act(root, "after"))
    one_slot(root, "          use: [backup]\n          on_failure: true")
    res, ev = run(root)
    assert not res.success and "backup" not in log(root)
    assert kinds(ev, "fallback_blocked")[0]["reason"] == \
        "step 'send' (python) had already acted outside Hydra ETL"
    # undo: none déclare qu'il n'y a rien à défaire : la bascule a lieu
    (root / "log.txt").unlink()
    main("  undo: none")
    res, _ = run(root)
    assert res.success and log(root) == ["send", "fail", "backup", "after"]


def test_rollback_done_allows_the_switch(root):
    wf(root, "main", """\
        - name: load1
          type: job
          job: ../jobs/j1
        - name: last
          type: job
          job: ../jobs/broken
          depends_on: [load1]
        """, rollback=True)
    wf(root, "backup", act(root, "backup"))
    wf(root, "after", act(root, "after"))
    one_slot(root, "          use: [backup]\n          on_failure: true")
    res, ev = run(root)
    assert res.success and log(root) == ["backup", "after"]
    assert res.runs[0].status == RECOVERED
    assert res.runs[0].result.rollback["status"] == "done"
    # load1 a été défait avant le départ du remplaçant
    assert (root / "data" / "out1.csv").read_text(encoding="utf-8") == "id,v\nold,1\n"


def test_failed_atomic_job_alone_counts_as_nothing_published(root):
    wf(root, "main", "- name: last\n  type: job\n  job: ../jobs/broken\n")
    wf(root, "backup", act(root, "backup"))
    wf(root, "after", act(root, "after"))
    one_slot(root, "          use: [backup]\n          on_failure: true")
    res, _ = run(root)
    assert res.success and log(root) == ["backup", "after"]


def test_next_backup_is_tried_when_the_first_fails(root):
    wf(root, "main", act(root, "main", FAIL))
    wf(root, "b1", act(root, "b1", FAIL))
    wf(root, "b2", act(root, "b2"))
    wf(root, "after", act(root, "after"))
    one_slot(root, "          use: [b1, b2]\n          on_failure: true")
    res, ev = run(root)
    assert res.success and log(root) == ["main", "b1", "b2", "after"]
    assert [(r.name, r.status) for r in res.runs[:3]] == [
        ("main", RECOVERED), ("b1", RECOVERED), ("b2", SUCCESS)]
    assert all(r.replaces == "main" for r in res.runs[1:3])
    assert [d["use"] for d in kinds(ev, "fallback")] == ["b1", "b2"]


def test_every_backup_fails(root):
    wf(root, "main", act(root, "main", FAIL))
    wf(root, "b1", act(root, "b1", FAIL))
    wf(root, "after", act(root, "after"))
    one_slot(root, "          use: [b1]\n          on_failure: true")
    res, ev = run(root)
    assert not res.success and log(root) == ["main", "b1"]
    assert [r.status for r in res.runs[:2]] == [RECOVERED, FAILED]
    assert kinds(ev, "fallback_blocked")[0]["reason"] == "no backup workflow left in fallback.use"
    assert [r.name for r in res.failed] == ["b1"]


def test_when_switch_then_failure_tries_the_next_backup(root):
    wf(root, "main", act(root, "main"))
    wf(root, "b1", act(root, "b1", FAIL))
    wf(root, "b2", act(root, "b2"))
    wf(root, "after", act(root, "after"))
    one_slot(root, '          use: [b1, b2]\n          when: "not file_exists(\'nope.txt\')"\n'
                   '          on_failure: true')
    res, ev = run(root)
    assert res.success and log(root) == ["b1", "b2", "after"]
    assert [d["trigger"] for d in kinds(ev, "fallback")] == ["when", "failure"]


def test_left_journal_blocks_the_switch(root):
    wf(root, "main", act(root, "main", FAIL))
    wf(root, "backup", act(root, "backup"))
    wf(root, "after", act(root, "after"))
    one_slot(root, "          use: [backup]\n          on_failure: true")
    j = root / ".hydra" / "undo" / "main.json"
    j.parent.mkdir(parents=True)
    j.write_text("{}", encoding="utf-8")
    res, ev = run(root)
    assert not res.success and log(root) == []
    assert "left changes to undo" in kinds(ev, "fallback_blocked")[0]["reason"]


def test_parallel_stage_with_a_recovered_workflow(root):
    wf(root, "a", act(root, "a", FAIL))
    wf(root, "a_backup", act(root, "a_backup"))
    wf(root, "b", act(root, "b"))
    thread(root, """\
          - mode: parallel
            workflows:
              - name: a
                fallback:
                  use: [a_backup]
                  on_failure: true
              - name: b
        """)
    res, _ = run(root)
    assert res.success
    assert sorted(log(root)) == ["a", "a_backup", "b"]
    assert {r.name: r.status for r in res.runs} == {"a": RECOVERED, "a_backup": SUCCESS, "b": SUCCESS}


# ── timeout ─────────────────────────────────────────────────────────────────

SLOW = "import time; time.sleep(1.0)"


def slow_then_mark(root: Path, name: str) -> str:
    return act(root, name, SLOW, step="slow").rstrip() + "\n" + f"""\
        - name: mark
          type: action
          action: python
          params:
            script: {py(root, name + "_mark")}
          undo: none
          depends_on: [slow]
        """


def test_timeout_fails_the_workflow(root):
    wf(root, "main", slow_then_mark(root, "main"))
    wf(root, "after", act(root, "after"))
    thread(root, """\
          - mode: sequential
            workflows:
              - name: main
                timeout: 300ms
              - name: after
        """)
    res, ev = run(root)
    assert not res.success
    main = res.runs[0]
    assert main.status == FAILED and main.timed_out
    assert main.error.startswith("timed out after 300ms")
    assert log(root) == ["main"]                   # mark (step suivant) jamais lancé
    assert kinds(ev, "timeout")[0]["seconds"] == pytest.approx(0.3)


def test_timeout_triggers_the_fallback(root):
    wf(root, "main", slow_then_mark(root, "main"))
    wf(root, "backup", act(root, "backup"))
    wf(root, "after", act(root, "after"))
    one_slot(root, "          use: [backup]\n          on_failure: true",
             extra="        timeout: 300ms\n")
    res, ev = run(root)
    assert res.success and log(root) == ["main", "backup", "after"]
    fb = kinds(ev, "fallback")[0]
    assert fb["trigger"] == "timeout" and "main timed out without publishing anything" in fb["reason"]


def test_fast_workflow_is_not_affected_by_timeout(root):
    wf(root, "main", act(root, "main"))
    thread(root, "  - workflows:\n      - name: main\n        timeout: 1h\n")
    res, ev = run(root)
    assert res.success and not res.runs[0].timed_out and not kinds(ev, "timeout")


def test_stop_signal_cancels_an_atomic_load(root):
    stop = StopSignal()
    stop.stop("timed out after 1s")
    r = JobExecutor(job_dir=root / "jobs" / "j1", root_dir=root, stop=stop).run()
    assert not r.success and "timed out after 1s" in r.error
    assert (root / "data" / "out1.csv").read_text(encoding="utf-8") == "id,v\nold,1\n"


# ── published_by (cas non couverts par un vrai run) ─────────────────────────

class _JR:
    def __init__(self, partial):
        self.partial_write = partial


class _SR:
    def __init__(self, name, success, jr=None):
        self.step_name, self.success, self.job_result = name, success, jr
        self.skipped, self.undo_of = False, None


class _Res:
    def __init__(self, steps, rollback=None):
        self.steps, self.rollback = steps, rollback


def test_published_by_partial_write_and_rollback_failed():
    r = WorkflowRun("w", 1, FAILED, result=_Res([_SR("load", False, _JR(True))]))
    assert "left part of its data written" in published_by(r)
    r = WorkflowRun("w", 1, FAILED, result=_Res([], rollback={"status": "failed",
                    "steps": [{"step": "load", "status": "failed", "message": "db down"}]}))
    assert published_by(r) == "its rollback stopped (db down)"
    r = WorkflowRun("w", 1, FAILED, result=_Res([_SR("load", False, _JR(False))]))
    assert published_by(r) is None


# ── thread.yaml, dry-run ────────────────────────────────────────────────────

def test_timeout_format_and_render(tmp_path):
    t = ThreadDef.model_validate({"thread": [{"workflows": [{"name": "a", "timeout": "30m"}]}]})
    w = t.thread[0].workflows[0]
    assert w.timeout_seconds == 1800
    assert "        timeout: 30m" in render_thread(t)
    for bad in ("0", 0, "abc", "-5"):
        with pytest.raises(Exception):
            ThreadDef.model_validate({"thread": [{"workflows": [{"name": "a", "timeout": bad}]}]})
    p = tmp_path / "thread.yaml"
    p.write_text(render_thread(t), encoding="utf-8")
    assert load_thread(p).thread[0].workflows[0].timeout == "30m"


def test_dry_run_warns_on_failure_without_rollback(root):
    wf(root, "main", """\
        - name: load1
          type: job
          job: ../jobs/j1
        - name: notify
          type: action
          action: python
          params:
            script: "print(1)"
          depends_on: [load1]
        """)
    wf(root, "backup", act(root, "backup"))
    wf(root, "after", act(root, "after"))
    one_slot(root, "          use: [backup]\n          on_failure: true", extra="        timeout: 5m\n")
    plan = prepare_project(root)
    assert any("publishes in 2 steps (load1, notify) without rollback: true" in w for w in plan.warnings)
    out = CliRunner().invoke(cli, ["run", str(root), "--dry-run"]).output
    assert "without rollback: true" in out and "timeout 5m" in out


# ── Run lancé depuis Studio (API) ───────────────────────────────────────────

def test_studio_run_shows_the_recovered_workflow(root, tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    import time
    from fastapi.testclient import TestClient
    from hydra_etl.api import store
    monkeypatch.setattr(store, "WORKSPACE", tmp_path / "ws")
    monkeypatch.setattr(store, "_INDEX_FILE", tmp_path / "ws" / "index.json")
    (tmp_path / "ws").mkdir()
    import hydra_etl.api.main as main
    client = TestClient(main.app)
    wf(root, "main", act(root, "main", FAIL))
    wf(root, "backup", act(root, "backup"))
    wf(root, "after", act(root, "after"))
    one_slot(root, "          use: [backup]\n          on_failure: true", extra="        timeout: 1h\n")
    proj = store.open_project(str(root))
    rid = client.post("/api/runs", json={"workflow_path": str(root)}).json()["run_id"]
    for _ in range(100):
        run_ = client.get(f"/api/runs/{rid}").json()
        if run_["status"] in ("success", "failed"):
            break
        time.sleep(0.1)
    assert run_["status"] == "success"
    main_step, backup_step = run_["steps"][0], run_["steps"][1]
    assert main_step["success"] is False and main_step["recovered_by"] == "backup"
    assert backup_step["step_name"] == "backup — fallback of main"
    assert backup_step["fallback"]["trigger"] == "failure"
    assert backup_step["logs"][0].startswith("FALLBACK main -> backup (failure): main failed without")
    # le thread enregistré par Studio garde timeout
    th = client.get(f"/api/projects/{proj.id}/thread").json()
    assert th["thread"]["thread"][0]["workflows"][0]["timeout"] == "1h"
    th["thread"]["thread"][0]["workflows"][0]["timeout"] = "45m"
    assert client.put(f"/api/projects/{proj.id}/thread", json=th["thread"]).status_code == 200
    assert "        timeout: 45m" in (root / "workflows" / "thread.yaml").read_text(encoding="utf-8")
