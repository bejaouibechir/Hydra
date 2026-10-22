"""`hdrctl job add | attach | detach` : les jobs d'un projet et leur place dans
les workflows. Dans un workflow, les steps forment une chaîne séquentielle."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from hydra_etl.cli.hdrctl import cli
from hydra_etl.workflow.jobs import attach_job, detach_job, dump_workflow, job_usage
from hydra_etl.workflow.parser import load_workflow
from hydra_etl.workflow.project import ProjectError, add_workflow


@pytest.fixture
def runner():
    return CliRunner(env={"HYDRA_LANG": "en"})


@pytest.fixture
def proj(tmp_path, runner, monkeypatch):
    root = tmp_path / "proj"
    assert runner.invoke(cli, ["init", str(root), "-q"]).exit_code == 0
    monkeypatch.chdir(root)
    return root


def chain(root: Path, wf: str = "workflow1") -> list:
    """[(step, job, depends_on)] dans l'ordre du fichier, après validation."""
    path = root / "workflows" / f"{wf}.yaml"
    load_workflow(path)                                   # toujours valide
    steps = yaml.safe_load(path.read_text(encoding="utf-8"))["workflow"]["steps"]
    return [(s["name"], s.get("job"), s.get("depends_on", [])) for s in steps]


def mkjob(runner, name):
    assert runner.invoke(cli, ["job", "add", name]).exit_code == 0


# ── add ───────────────────────────────────────────────────────────────────────

def test_add_free_job(runner, proj):
    res = runner.invoke(cli, ["job", "add", "load_orders"])
    assert res.exit_code == 0, res.output
    for f in ("sources.yaml", "destinations.yaml", "pipeline.yaml", "transformations.yaml", "README.md"):
        assert (proj / "jobs" / "load_orders" / f).is_file(), f
    assert "not in any workflow" in res.output
    assert job_usage(proj, "load_orders") == {}


def test_add_with_template(runner, proj):
    assert runner.invoke(cli, ["job", "add", "db", "--template", "mysql"]).exit_code == 0
    assert (proj / "jobs" / "db" / ".env.example").is_file()


def test_add_to_workflow_appends_to_chain(runner, proj):
    res = runner.invoke(cli, ["job", "add", "load_orders", "workflow1"])
    assert res.exit_code == 0, res.output
    assert chain(proj) == [("job1", "../jobs/job1", []),
                           ("load_orders", "../jobs/load_orders", ["job1"])]
    assert "Runs after step 'job1'" in res.output


def test_add_at_position_1_rewires_old_first(runner, proj):
    res = runner.invoke(cli, ["job", "add", "extract", "workflow1", "-p", "1"])
    assert res.exit_code == 0, res.output
    assert chain(proj) == [("extract", "../jobs/extract", []),
                           ("job1", "../jobs/job1", ["extract"])]


def test_add_in_the_middle(runner, proj):
    runner.invoke(cli, ["job", "add", "c", "workflow1"])
    runner.invoke(cli, ["job", "add", "b", "workflow1", "--position", "2"])
    assert [(n, d) for n, _, d in chain(proj)] == [("job1", []), ("b", ["job1"]), ("c", ["b"])]


@pytest.mark.parametrize("args,fragment", [
    (["job", "add", "x", "workflow1", "-p", "5"], "out of range"),
    (["job", "add", "x", "workflow1", "-p", "0"], "out of range"),
    (["job", "add", "x", "-p", "1"], "needs a WORKFLOW"),
    (["job", "add", "x", "ghost"], "not found"),
    (["job", "add", "job1"], "already exists"),
    (["job", "add", "../x"], "invalid job name"),
])
def test_add_errors_create_nothing(runner, proj, args, fragment):
    before = (proj / "workflows" / "workflow1.yaml").read_text(encoding="utf-8")
    res = runner.invoke(cli, args)
    assert res.exit_code == 1
    assert fragment in res.output
    assert not (proj / "jobs" / "x").exists()
    assert (proj / "workflows" / "workflow1.yaml").read_text(encoding="utf-8") == before


def test_outside_project(runner, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for args in (["job", "add", "x"], ["job", "attach", "x", "w"], ["job", "detach", "x"]):
        res = runner.invoke(cli, args)
        assert res.exit_code == 1 and "--project" in res.output
    assert not (tmp_path / "jobs").exists()


def test_project_option(runner, proj, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    res = runner.invoke(cli, ["job", "add", "remote", "workflow1", "--project", str(proj)])
    assert res.exit_code == 0, res.output
    assert chain(proj)[-1][0] == "remote"


# ── attach ────────────────────────────────────────────────────────────────────

def test_attach_existing_job(runner, proj):
    mkjob(runner, "a")
    add_workflow(proj, "w2")
    assert runner.invoke(cli, ["job", "attach", "a", "w2"]).exit_code == 0
    assert runner.invoke(cli, ["job", "attach", "job1", "w2"]).exit_code == 0
    assert [(n, d) for n, _, d in chain(proj, "w2")] == [("a", []), ("job1", ["a"])]
    assert sorted(job_usage(proj, "job1")) == ["w2", "workflow1"]


def test_attach_twice_is_refused(runner, proj):
    res = runner.invoke(cli, ["job", "attach", "job1", "workflow1"])
    assert res.exit_code == 1 and "already attached" in res.output


def test_attach_missing_job_or_workflow(runner, proj):
    assert "job add ghost" in runner.invoke(cli, ["job", "attach", "ghost", "workflow1"]).output
    res = runner.invoke(cli, ["job", "attach", "job1", "nowf"])
    assert res.exit_code == 1 and "workflow add nowf" in res.output


def test_attach_step_name_collision(proj, runner):
    wf = proj / "workflows" / "workflow1.yaml"
    doc = yaml.safe_load(wf.read_text(encoding="utf-8"))
    doc["workflow"]["steps"].append({"name": "load", "type": "action", "action": "log",
                                     "params": {"message": "hi"}, "depends_on": ["job1"]})
    wf.write_text(dump_workflow(doc), encoding="utf-8")
    mkjob(runner, "load")
    res = attach_job(proj, "load", "workflow1")
    assert res.step == "load-2"
    assert chain(proj)[-1] == ("load-2", "../jobs/load", ["load"])


def test_attach_keeps_other_fields(proj, runner):
    wf = proj / "workflows" / "workflow1.yaml"
    wf.write_text(textwrap.dedent("""\
        version: "1.0"
        workflow:
          name: workflow1
          description: keep me
          trigger:
            type: schedule
            cron: "0 6 * * *"
          steps:
            - name: job1
              type: job
              job: ../jobs/job1
              retry:
                max: 2
            - name: notify
              type: action
              action: log
              params:
                message: "done {{ param:x }}"
              depends_on: [job1]
              on_failure: continue
        """), encoding="utf-8")
    mkjob(runner, "b")
    attach_job(proj, "b", "workflow1", position=2)
    doc = yaml.safe_load(wf.read_text(encoding="utf-8"))
    assert doc["version"] == "1.0"
    w = doc["workflow"]
    assert w["description"] == "keep me" and w["trigger"] == {"type": "schedule", "cron": "0 6 * * *"}
    assert w["steps"][0]["retry"] == {"max": 2}
    assert w["steps"][2]["params"] == {"message": "done {{ param:x }}"}
    assert w["steps"][2]["on_failure"] == "continue"
    assert [(n, d) for n, _, d in chain(proj)] == [("job1", []), ("b", ["job1"]), ("notify", ["b"])]


def test_attach_before_non_chained_step_warns(proj, runner):
    wf = proj / "workflows" / "workflow1.yaml"
    doc = yaml.safe_load(wf.read_text(encoding="utf-8"))
    doc["workflow"]["steps"].append({"name": "side", "type": "action", "action": "log",
                                     "params": {"message": "x"}, "depends_on": []})
    wf.write_text(dump_workflow(doc), encoding="utf-8")
    mkjob(runner, "b")
    res = runner.invoke(cli, ["job", "attach", "b", "workflow1", "-p", "2"])
    assert res.exit_code == 0
    assert "left as is" in res.output
    assert [(n, d) for n, _, d in chain(proj)] == [("job1", []), ("b", ["job1"]), ("side", [])]


# ── detach ────────────────────────────────────────────────────────────────────

def test_detach_middle_keeps_chain(runner, proj):
    runner.invoke(cli, ["job", "add", "b", "workflow1"])
    runner.invoke(cli, ["job", "add", "c", "workflow1"])
    res = runner.invoke(cli, ["job", "detach", "b", "workflow1"])
    assert res.exit_code == 0, res.output
    assert [(n, d) for n, _, d in chain(proj)] == [("job1", []), ("c", ["job1"])]
    assert "now depends on: job1" in res.output
    assert (proj / "jobs" / "b").is_dir()                 # le dossier reste


def test_detach_first(runner, proj):
    runner.invoke(cli, ["job", "add", "b", "workflow1"])
    runner.invoke(cli, ["job", "detach", "job1", "workflow1"])
    assert [(n, d) for n, _, d in chain(proj)] == [("b", [])]


def test_detach_fan_in_dedupes(proj, runner):
    wf = proj / "workflows" / "workflow1.yaml"
    for n in ("a", "b"):
        mkjob(runner, n)
    wf.write_text(textwrap.dedent("""\
        workflow:
          name: workflow1
          steps:
            - {name: job1, type: job, job: ../jobs/job1}
            - {name: a, type: job, job: ../jobs/a, depends_on: [job1]}
            - {name: b, type: job, job: ../jobs/b, depends_on: [job1, a]}
        """), encoding="utf-8")
    detach_job(proj, "a", "workflow1")
    assert [(n, d) for n, _, d in chain(proj)] == [("job1", []), ("b", ["job1"])]


def test_detach_from_all_workflows(runner, proj):
    add_workflow(proj, "w2")
    runner.invoke(cli, ["job", "attach", "job1", "w2"])
    res = runner.invoke(cli, ["job", "detach", "job1"])
    assert res.exit_code == 0, res.output
    assert job_usage(proj, "job1") == {}
    assert "now free" in res.output
    assert chain(proj) == [] and chain(proj, "w2") == []


def test_detach_messages(runner, proj):
    add_workflow(proj, "w2")
    res = runner.invoke(cli, ["job", "detach", "job1", "w2"])
    assert res.exit_code == 0 and "not attached to workflow 'w2'" in res.output and "workflow1" in res.output
    mkjob(runner, "lonely")
    res = runner.invoke(cli, ["job", "detach", "lonely"])
    assert res.exit_code == 0 and "free" in res.output
    res = runner.invoke(cli, ["job", "detach", "ghost"])
    assert res.exit_code == 1 and "not found" in res.output
    res = runner.invoke(cli, ["job", "detach", "job1", "nowf"])
    assert res.exit_code == 1


def test_project_still_runs_after_changes(runner, proj):
    runner.invoke(cli, ["job", "add", "b", "workflow1", "-p", "1"])
    runner.invoke(cli, ["job", "detach", "job1"])
    res = runner.invoke(cli, ["run", ".", "--dry-run"])
    assert res.exit_code == 0, res.output
    res = runner.invoke(cli, ["run", "."])
    assert res.exit_code == 0, res.output


def test_workflow_add_suggests_job_attach(runner, proj):
    res = runner.invoke(cli, ["workflow", "add", "w9"])
    assert "hdrctl job attach <job> w9" in res.output


# ── API : endpoints miroirs de la CLI ─────────────────────────────────────────

def test_api_job_and_workflow_endpoints(tmp_path, runner):
    pytest.importorskip("fastapi")
    from hydra_etl.api.routers import jobs as r
    root = tmp_path / "apiproj"
    assert runner.invoke(cli, ["init", str(root), "-q"]).exit_code == 0
    P = str(root)
    assert r.add_workflow_cli(r.WorkflowAddRequest(project=P, name="w2")).success
    res = r.add_job_cli(r.JobAddRequest(project=P, name="a", workflow="w2"))
    assert res.success, res.stdout + res.stderr
    assert r.attach_job_cli(r.JobAttachRequest(project=P, name="job1", workflow="w2", position=1)).success
    assert [(n, d) for n, _, d in chain(root, "w2")] == [("job1", []), ("a", ["job1"])]
    assert r.detach_job_cli(r.JobDetachRequest(project=P, name="job1")).success
    assert chain(root, "w2") == [("a", "../jobs/a", [])] and chain(root) == []
    assert r.remove_workflow_cli(r.WorkflowRemoveRequest(project=P, name="w2")).success
    assert not (root / "workflows" / "w2.yaml").exists()
    assert not r.attach_job_cli(r.JobAttachRequest(project=P, name="ghost", workflow="workflow1")).success


# ── job list / hdrctl list <projet> ───────────────────────────────────────────

def _overview_project(runner, proj):
    runner.invoke(cli, ["job", "add", "a", "workflow1"])
    runner.invoke(cli, ["job", "add", "lonely"])
    (proj / "jobs" / "broken").mkdir()
    add_workflow(proj, "w2")
    attach_job(proj, "a", "w2")
    wf = proj / "workflows" / "w2.yaml"
    doc = yaml.safe_load(wf.read_text(encoding="utf-8"))
    doc["workflow"]["steps"].append({"name": "g", "type": "job", "job": "../jobs/ghost", "depends_on": ["a"]})
    wf.write_text(dump_workflow(doc), encoding="utf-8")


def test_jobs_overview(runner, proj):
    from hydra_etl.workflow.jobs import jobs_overview
    _overview_project(runner, proj)
    got = {i.name: (i.exists, i.missing, sorted(w for w, _ in i.used_by)) for i in jobs_overview(proj)}
    assert got == {
        "a": (True, [], ["w2", "workflow1"]),
        "broken": (True, ["sources.yaml", "destinations.yaml", "pipeline.yaml"], []),
        "job1": (True, [], ["workflow1"]),
        "lonely": (True, [], []),
        "ghost": (False, [], ["w2"]),
    }


@pytest.mark.parametrize("args", [["job", "list"], ["list"], ["list", "."]])
def test_job_list_and_list_on_project(runner, proj, args):
    _overview_project(runner, proj)
    res = runner.invoke(cli, args)
    assert res.exit_code == 0, res.output
    out = res.output
    assert "Jobs of project" in out
    assert "in: w2, workflow1" in out
    assert "free (in no workflow)" in out
    assert "missing: sources.yaml" in out
    assert "folder missing, used by: w2" in out
    assert "4 job(s), 1 free" in out
    assert "No jobs found" not in out


def test_job_list_outside_project(runner, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    res = runner.invoke(cli, ["job", "list"])
    assert res.exit_code == 1 and "--project" in res.output


def test_job_list_with_project_option(runner, proj, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    res = runner.invoke(cli, ["job", "list", "--project", str(proj)])
    assert res.exit_code == 0 and "job1" in res.output
