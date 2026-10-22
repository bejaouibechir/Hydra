"""`hdrctl run <projet>` : exécution d'un projet entier selon workflows/thread.yaml."""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
from click.testing import CliRunner

from hydra_etl.cli.hdrctl import cli
from hydra_etl.workflow.project import (
    FAILED, INACTIVE, NOT_RUN, SUCCESS, ProjectError, ProjectRunner,
    find_project_root, prepare_project, resolve_thread,
)


@pytest.fixture
def runner():
    return CliRunner()


def _project(tmp_path: Path, runner: CliRunner) -> Path:
    root = tmp_path / "proj"
    assert runner.invoke(cli, ["init", str(root), "-q"]).exit_code == 0
    return root


def _action_wf(root: Path, name: str, code: str = "", fail: bool = False) -> None:
    """Workflow à une action python qui ajoute une ligne `<name> <greeting>` à log.txt."""
    log = (root / "log.txt").as_posix()
    script = code or (f"open(r'{log}', 'a').write('{name} {{{{ param:greeting }}}}\\n')"
                      + ("; import sys; sys.exit(2)" if fail else ""))
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


def _thread(root: Path, body: str) -> None:
    (root / "workflows" / "thread.yaml").write_text(
        'version: "1.0"\nthread:\n' + textwrap.dedent(body), encoding="utf-8")


def _params(root: Path) -> None:
    (root / "parameters.yaml").write_text(
        'version: "1.0"\nparameters:\n  greeting:\n    type: string\n    default: dflt\n',
        encoding="utf-8")
    (root / "environments" / "prod.yaml").write_text(
        'version: "1.0"\nparameters:\n  greeting: prod\n', encoding="utf-8")


def _log(root: Path) -> list[str]:
    f = root / "log.txt"
    return f.read_text(encoding="utf-8").splitlines() if f.exists() else []


# ── Découverte ────────────────────────────────────────────────────────────────

def test_find_project_root(tmp_path, runner):
    root = _project(tmp_path, runner)
    assert find_project_root(root / "jobs" / "job1") == root.resolve()
    assert find_project_root(root / "workflows") == root.resolve()
    assert find_project_root(tmp_path) is None


def test_resolve_thread_without_file_is_alphabetical(tmp_path, runner):
    root = _project(tmp_path, runner)
    (root / "workflows" / "thread.yaml").unlink()
    _action_wf(root, "zeta")
    _action_wf(root, "alpha")
    th, implicit = resolve_thread(root)
    assert implicit is True
    assert th.workflow_names() == ["alpha", "workflow1", "zeta"]
    assert th.thread[0].mode == "sequential"


# ── Validation avant exécution ────────────────────────────────────────────────

def test_prepare_rejects_non_project(tmp_path):
    with pytest.raises(ProjectError, match="not a Hydra project"):
        prepare_project(tmp_path)


def test_prepare_reports_every_problem(tmp_path, runner):
    root = _project(tmp_path, runner)
    _thread(root, """\
        - workflows:
            - name: workflow1
            - name: ghost
        """)
    with pytest.raises(ProjectError) as e:
        prepare_project(root)
    assert any("ghost" in m for m in e.value.errors)


def test_prepare_reports_invalid_manifest_and_missing_job(tmp_path, runner):
    root = _project(tmp_path, runner)
    (root / "workflows" / "bad.yaml").write_text("workflow:\n  name: bad\n  steps: nope\n", encoding="utf-8")
    (root / "workflows" / "nojob.yaml").write_text(textwrap.dedent("""\
        workflow:
          name: nojob
          steps:
            - name: j
              type: job
              job: ../jobs/missing
        """), encoding="utf-8")
    _thread(root, """\
        - workflows:
            - name: bad
            - name: nojob
        """)
    with pytest.raises(ProjectError) as e:
        prepare_project(root)
    msgs = " | ".join(e.value.errors)
    assert "bad.yaml" in msgs and "job folder not found" in msgs


def test_inactive_workflow_is_not_validated(tmp_path, runner):
    root = _project(tmp_path, runner)
    (root / "workflows" / "bad.yaml").write_text("workflow: {}\n", encoding="utf-8")
    _thread(root, """\
        - workflows:
            - name: workflow1
            - name: bad
              active: false
        """)
    assert prepare_project(root).active_names == ["workflow1"]


# ── Exécution ─────────────────────────────────────────────────────────────────

def test_sequential_order_inactive_and_delay(tmp_path, runner):
    root = _project(tmp_path, runner)
    _params(root)
    for n in ("a", "b", "c", "d"):
        _action_wf(root, n)
    _thread(root, """\
        - mode: sequential
          delay_after: 5m
          workflows:
            - name: b
            - name: c
              active: false
            - name: a
        - mode: sequential
          delay_after: 9s
          workflows:
            - name: d
        """)
    sleeps: list = []
    events: list = []
    result = ProjectRunner(prepare_project(root), sleep=sleeps.append).run(
        lambda kind, data: events.append(kind))
    assert result.success
    assert _log(root) == ["b dflt", "a dflt", "d dflt"]
    assert [(r.name, r.status) for r in result.runs] == [
        ("b", SUCCESS), ("c", INACTIVE), ("a", SUCCESS), ("d", SUCCESS)]
    assert sleeps == [300.0]          # pas d'attente après la dernière étape
    assert events.count("stage") == 2 and "delay" in events


def test_parallel_stage_runs_all(tmp_path, runner):
    root = _project(tmp_path, runner)
    _params(root)
    for n in ("p1", "p2", "p3"):
        _action_wf(root, n)
    _thread(root, """\
        - mode: parallel
          workflows:
            - name: p1
            - name: p2
            - name: p3
        """)
    result = ProjectRunner(prepare_project(root)).run()
    assert result.success
    assert sorted(_log(root)) == ["p1 dflt", "p2 dflt", "p3 dflt"]


def test_failure_stops_the_project(tmp_path, runner):
    root = _project(tmp_path, runner)
    _params(root)
    _action_wf(root, "ok1")
    _action_wf(root, "boom", fail=True)
    _action_wf(root, "after")
    _action_wf(root, "later")
    _thread(root, """\
        - workflows:
            - name: ok1
            - name: boom
            - name: after
        - workflows:
            - name: later
        """)
    sleeps: list = []
    result = ProjectRunner(prepare_project(root), sleep=sleeps.append).run()
    assert not result.success
    assert [(r.name, r.status) for r in result.runs] == [
        ("ok1", SUCCESS), ("boom", FAILED), ("after", NOT_RUN), ("later", NOT_RUN)]
    assert [r.name for r in result.failed] == ["boom"]
    assert _log(root) == ["ok1 dflt", "boom dflt"]


def test_parallel_failure_lets_siblings_finish_then_stops(tmp_path, runner):
    root = _project(tmp_path, runner)
    _params(root)
    _action_wf(root, "x", fail=True)
    _action_wf(root, "y")
    _action_wf(root, "z")
    _thread(root, """\
        - mode: parallel
          workflows:
            - name: x
            - name: y
        - workflows:
            - name: z
        """)
    result = ProjectRunner(prepare_project(root)).run()
    status = {r.name: r.status for r in result.runs}
    assert status == {"x": FAILED, "y": SUCCESS, "z": NOT_RUN}


@pytest.mark.parametrize("env,params,expected", [
    (None, None, "dflt"),
    ("prod", None, "prod"),
    ("prod", {"greeting": "cli"}, "cli"),
])
def test_parameter_precedence(tmp_path, runner, env, params, expected):
    root = _project(tmp_path, runner)
    _params(root)
    _action_wf(root, "w")
    _thread(root, "- workflows:\n    - name: w\n")
    assert ProjectRunner(prepare_project(root), env=env, params=params).run().success
    assert _log(root) == [f"w {expected}"]


def test_workflow_run_reads_project_parameters(tmp_path, runner):
    """Régression : un workflow rangé dans workflows/ lit parameters.yaml et
    environments/ à la racine du projet (avant : cherchés dans workflows/)."""
    root = _project(tmp_path, runner)
    _params(root)
    _action_wf(root, "solo")
    res = runner.invoke(cli, ["workflow", "run", str(root / "workflows" / "solo.yaml")])
    assert res.exit_code == 0, res.output
    assert _log(root) == ["solo dflt"]


def test_python_file_path_falls_back_to_project_root(tmp_path, runner):
    root = _project(tmp_path, runner)
    out = (root / "log.txt").as_posix()
    (root / "scripts" / "hello.py").write_text(f"open(r'{out}', 'a').write('script\\n')\n", encoding="utf-8")
    (root / "workflows" / "s.yaml").write_text(textwrap.dedent("""\
        workflow:
          name: s
          steps:
            - name: run
              type: action
              action: python
              params:
                file_path: scripts/hello.py
        """), encoding="utf-8")
    _thread(root, "- workflows:\n    - name: s\n")
    assert ProjectRunner(prepare_project(root)).run().success
    assert _log(root) == ["script"]


# ── CLI ───────────────────────────────────────────────────────────────────────

def test_cli_run_project(tmp_path, runner):
    root = _project(tmp_path, runner)
    res = runner.invoke(cli, ["run", str(root)])
    assert res.exit_code == 0, res.output
    assert "workflow1" in res.output
    assert (root / "jobs" / "job1" / "data" / "output.csv").exists()


def test_cli_run_dot(tmp_path, runner, monkeypatch):
    root = _project(tmp_path, runner)
    monkeypatch.chdir(root)
    res = runner.invoke(cli, ["run", "."])
    assert res.exit_code == 0, res.output


def test_cli_dry_run_executes_nothing(tmp_path, runner):
    root = _project(tmp_path, runner)
    _params(root)
    _action_wf(root, "w")
    _thread(root, """\
        - workflows:
            - name: workflow1
            - name: w
              active: false
        """)
    res = runner.invoke(cli, ["run", str(root), "--dry-run", "--lang", "en"])
    assert res.exit_code == 0, res.output
    assert "Execution plan" in res.output and "inactive" in res.output
    assert not (root / "jobs" / "job1" / "data" / "output.csv").exists()
    assert _log(root) == []


def test_cli_invalid_project_exits_1_and_runs_nothing(tmp_path, runner):
    root = _project(tmp_path, runner)
    _params(root)
    _action_wf(root, "w")
    _thread(root, """\
        - workflows:
            - name: w
            - name: ghost
        """)
    res = runner.invoke(cli, ["run", str(root)])
    assert res.exit_code == 1
    assert "ghost" in res.output
    assert _log(root) == []


def test_cli_failure_exit_code_and_hooks(tmp_path, runner):
    root = _project(tmp_path, runner)
    _params(root)
    _action_wf(root, "boom", fail=True)
    _thread(root, "- workflows:\n    - name: boom\n")
    res = runner.invoke(cli, ["run", str(root), "--on-failure", "echo FAILHOOK",
                              "--on-success", "echo OKHOOK", "--on-finish", "echo FINHOOK"])
    assert res.exit_code == 1
    assert "on-failure" in res.output and "on-finish" in res.output
    assert "on-success" not in res.output


@pytest.mark.parametrize("opt", [["-s", "x.yaml"], ["--profile"]])
def test_cli_job_only_options_rejected_for_project(tmp_path, runner, opt):
    root = _project(tmp_path, runner)
    res = runner.invoke(cli, ["run", str(root), *opt])
    assert res.exit_code == 1
    assert "jobs/<job>" in res.output


def test_cli_job_mode_unchanged(tmp_path, runner):
    root = _project(tmp_path, runner)
    res = runner.invoke(cli, ["run", str(root / "jobs" / "job1")])
    assert res.exit_code == 0, res.output


def test_cli_no_active_workflow(tmp_path, runner):
    root = _project(tmp_path, runner)
    _thread(root, "- workflows:\n    - name: workflow1\n      active: false\n")
    res = runner.invoke(cli, ["run", str(root), "--lang", "en"])
    assert res.exit_code == 0
    assert "nothing to run" in res.output


# ── Boucles ───────────────────────────────────────────────────────────────────

def _loop_project(tmp_path, runner, body, fail=()):
    root = _project(tmp_path, runner)
    _params(root)
    for n in ("a", "b", "c", "d", "e"):
        _action_wf(root, n, fail=n in fail)
    (root / "workflows" / "thread.yaml").write_text('version: "1.0"\n' + textwrap.dedent(body), encoding="utf-8")
    return root


def test_loop_replays_the_part_n_times(tmp_path, runner):
    root = _loop_project(tmp_path, runner, """\
        thread:
          - workflows: [{name: a}, {name: b}]
          - mode: parallel
            delay_after: 7s
            workflows: [{name: c}, {name: d}]
          - workflows: [{name: e}]
        loops:
          - from: d
            to: b
            times: 3
            delay: 2m
        """)
    sleeps, events = [], []
    res = ProjectRunner(prepare_project(root), sleep=sleeps.append).run(lambda k, d: events.append((k, d)))
    assert res.success
    log = [ln.split()[0] for ln in _log(root)]
    assert log[0] == "a" and log[-1] == "e"
    assert log.count("b") == 3 and log.count("c") == 3 and log.count("d") == 3 and log.count("a") == 1
    # pause de boucle avant chaque reprise, puis délai d'étape une seule fois (vers e)
    assert sleeps == [120.0, 120.0, 7.0]
    loops = [d for k, d in events if k == "loop"]
    assert [(d["iteration"], d["iterations"]) for d in loops] == [(2, 3), (3, 3)]
    b_runs = [(r.iteration, r.iterations) for r in res.runs if r.name == "b"]
    assert b_runs == [(1, 3), (2, 3), (3, 3)]
    assert [r.iteration for r in res.runs if r.name == "e"] == [1]


def test_loop_on_a_single_workflow(tmp_path, runner):
    root = _loop_project(tmp_path, runner, """\
        thread:
          - workflows: [{name: a}, {name: b}]
        loops:
          - {from: a, to: a, times: 4}
        """)
    assert ProjectRunner(prepare_project(root), sleep=lambda s: None).run().success
    assert [ln.split()[0] for ln in _log(root)] == ["a", "a", "a", "a", "b"]


def test_failure_inside_a_loop_stops_everything(tmp_path, runner):
    root = _loop_project(tmp_path, runner, """\
        thread:
          - workflows: [{name: a}]
        """)
    # boom échoue au 2e passage : on fabrique un workflow qui échoue s'il a déjà tourné
    log = (root / "log.txt").as_posix()
    script = (f"import os,sys; p=r'{log}'; n=open(p).read().count('x') if os.path.exists(p) else 0; "
              f"open(p,'a').write('x'+chr(10)); sys.exit(1 if n>=1 else 0)")
    (root / "workflows" / "x.yaml").write_text(
        "workflow:\n  name: x\n  steps:\n    - name: s\n      type: action\n      action: python\n"
        f"      params:\n        script: {json.dumps(script)}\n", encoding="utf-8")
    (root / "workflows" / "thread.yaml").write_text(textwrap.dedent("""\
        thread:
          - workflows: [{name: x}, {name: e}]
        loops:
          - {from: x, to: x, times: 5}
        """), encoding="utf-8")
    res = ProjectRunner(prepare_project(root), sleep=lambda s: None).run()
    assert not res.success
    assert [(r.name, r.status, r.iteration) for r in res.runs] == [
        ("x", SUCCESS, 1), ("x", FAILED, 2), ("e", NOT_RUN, 1)]


def test_cli_shows_passes_and_dry_run_plan(tmp_path, runner):
    root = _loop_project(tmp_path, runner, """\
        thread:
          - workflows: [{name: a}]
        loops:
          - {from: a, to: a, times: 2, delay: 1}
        """)
    res = runner.invoke(cli, ["run", str(root), "--dry-run", "--lang", "en"])
    assert res.exit_code == 0 and "loop a → a, 2 pass(es), waiting 1s" in res.output
    res = runner.invoke(cli, ["run", str(root), "--lang", "en"])
    assert res.exit_code == 0, res.output
    assert "(pass 2/2)" in res.output and "Loop a → a: pass 2/2" in res.output


def test_remove_workflow_drops_its_loop(tmp_path, runner):
    root = _loop_project(tmp_path, runner, """\
        thread:
          - workflows: [{name: a}, {name: b}]
        loops:
          - {from: b, to: a, times: 2}
        """)
    res = runner.invoke(cli, ["workflow", "remove", "b", "-y", "--project", str(root)])
    assert res.exit_code == 0, res.output
    from hydra_etl.workflow.thread import load_thread
    assert load_thread(root / "workflows" / "thread.yaml").loops == []
