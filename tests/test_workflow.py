"""
Tests du Workflow Engine — Hydra ETL.

Couvre :
1. Models  — validation Pydantic (Trigger, WorkflowStep, WorkflowDef)
2. Parser  — load_workflow, validate_workflow
3. Runner  — séquentiel, parallèle, on_failure, cycles, skip transitif
4. CLI     — hdrctl workflow validate / run / list / init
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from click.testing import CliRunner

from hydra_etl.cli.hdrctl import cli
from hydra_etl.workflow.models import (
    Trigger,
    WorkflowDef,
    WorkflowResult,
    WorkflowStep,
)
from hydra_etl.workflow.parser import load_workflow, validate_workflow
from hydra_etl.workflow.runner import WorkflowRunner


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def write_workflow(tmp_path: Path, content: str) -> Path:
    """Écrit un workflow.yaml et retourne son chemin."""
    p = tmp_path / "workflow.yaml"
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


def make_job_dir(base: Path, name: str) -> Path:
    """Crée un mini job CSV valide dans base/name."""
    job = base / name
    job.mkdir(parents=True, exist_ok=True)
    (job / "sources.yaml").write_text(
        "sources:\n  src:\n    type: csv\n    extract:\n      table: input.csv\n      batch_size: 1000\n"
    ,
        encoding="utf-8")
    (job / "destinations.yaml").write_text(
        "destinations:\n  dst:\n    type: csv\n    load:\n      table: output.csv\n      mode: replace\n"
    ,
        encoding="utf-8")
    (job / "pipeline.yaml").write_text(
        "pipeline:\n  from: src\n  to: dst\n"
    ,
        encoding="utf-8")
    (job / "input.csv").write_text("id,val\n1,a\n2,b\n", encoding="utf-8")
    return job


SIMPLE_WF = """\
    workflow:
      name: "test_wf"
      trigger:
        type: manual
      steps:
        - name: "step_a"
          type: job
          job: "./jobs/extract"
          depends_on: []
          on_failure: fail
        - name: "step_b"
          type: job
          job: "./jobs/load"
          depends_on: ["step_a"]
          on_failure: fail
"""


# ═══════════════════════════════════════════════════════════════
# 1. Models
# ═══════════════════════════════════════════════════════════════

class TestTrigger:

    def test_manual_default(self):
        t = Trigger()
        assert t.type == "manual"

    def test_schedule_requires_cron(self):
        with pytest.raises(ValueError, match="cron"):
            Trigger(type="schedule")

    def test_schedule_with_cron_ok(self):
        t = Trigger(type="schedule", cron="0 8 * * *")
        assert t.cron == "0 8 * * *"

    def test_webhook_no_cron_needed(self):
        t = Trigger(type="webhook")
        assert t.type == "webhook"


class TestWorkflowStep:

    def test_job_step_ok(self):
        s = WorkflowStep(name="s", type="job", job="./jobs/extract")
        assert s.job == "./jobs/extract"

    def test_job_step_missing_job(self):
        with pytest.raises(ValueError, match="job"):
            WorkflowStep(name="s", type="job")

    def test_action_step_ok(self):
        s = WorkflowStep(name="n", type="action", action="log", params={"message": "ok"})
        assert s.action == "log"

    def test_action_step_missing_action(self):
        with pytest.raises(ValueError, match="action"):
            WorkflowStep(name="n", type="action")

    def test_depends_on_defaults_empty(self):
        s = WorkflowStep(name="s", type="job", job="./j")
        assert s.depends_on == []

    def test_on_failure_default(self):
        s = WorkflowStep(name="s", type="job", job="./j")
        assert s.on_failure == "fail"


class TestWorkflowDef:

    def test_valid(self):
        wf = WorkflowDef(
            name="wf",
            steps=[WorkflowStep(name="s", type="job", job="./j")],
        )
        assert wf.name == "wf"
        assert len(wf.steps) == 1

    def test_duplicate_names_rejected(self):
        with pytest.raises(ValueError, match="dupliqués"):
            WorkflowDef(
                name="wf",
                steps=[
                    WorkflowStep(name="dup", type="job", job="./j1"),
                    WorkflowStep(name="dup", type="job", job="./j2"),
                ],
            )

    def test_trigger_defaults_to_manual(self):
        wf = WorkflowDef(
            name="wf",
            steps=[WorkflowStep(name="s", type="job", job="./j")],
        )
        assert wf.trigger.type == "manual"


# ═══════════════════════════════════════════════════════════════
# 2. Parser
# ═══════════════════════════════════════════════════════════════

class TestLoadWorkflow:

    def test_load_valid(self, tmp_path):
        p = write_workflow(tmp_path, SIMPLE_WF)
        wf = load_workflow(p)
        assert wf.name == "test_wf"
        assert len(wf.steps) == 2

    def test_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_workflow(tmp_path / "missing.yaml")

    def test_missing_workflow_key(self, tmp_path):
        p = write_workflow(tmp_path, "name: oops\nsteps: []\n")
        with pytest.raises(ValueError, match="workflow"):
            load_workflow(p)

    def test_invalid_yaml(self, tmp_path):
        p = tmp_path / "workflow.yaml"
        p.write_text("workflow: {name: [bad: yaml: }\n", encoding="utf-8")
        with pytest.raises(ValueError):
            load_workflow(p)

    def test_schedule_trigger_parsed(self, tmp_path):
        p = write_workflow(tmp_path, """\
            workflow:
              name: sched
              trigger:
                type: schedule
                cron: "0 6 * * *"
              steps:
                - name: s
                  type: job
                  job: ./j
        """)
        wf = load_workflow(p)
        assert wf.trigger.type == "schedule"
        assert wf.trigger.cron == "0 6 * * *"

    def test_steps_depends_on_is_list(self, tmp_path):
        p = write_workflow(tmp_path, SIMPLE_WF)
        wf = load_workflow(p)
        assert isinstance(wf.steps[1].depends_on, list)
        assert wf.steps[1].depends_on == ["step_a"]


class TestValidateWorkflow:

    def test_valid_workflow(self, tmp_path):
        p = write_workflow(tmp_path, SIMPLE_WF)
        ok, msg = validate_workflow(p)
        assert ok is True
        assert msg == ""

    def test_cycle_detected(self, tmp_path):
        p = write_workflow(tmp_path, """\
            workflow:
              name: cycle_wf
              steps:
                - name: a
                  type: job
                  job: ./j
                  depends_on: [b]
                - name: b
                  type: job
                  job: ./j
                  depends_on: [a]
        """)
        ok, msg = validate_workflow(p)
        assert ok is False
        assert "ycle" in msg

    def test_unknown_dependency(self, tmp_path):
        p = write_workflow(tmp_path, """\
            workflow:
              name: bad
              steps:
                - name: a
                  type: job
                  job: ./j
                  depends_on: [nonexistent]
        """)
        ok, msg = validate_workflow(p)
        assert ok is False

    def test_file_not_found(self, tmp_path):
        ok, msg = validate_workflow(tmp_path / "ghost.yaml")
        assert ok is False
        assert "not found" in msg.lower() or "introuvable" in msg.lower()


# ═══════════════════════════════════════════════════════════════
# 3. Runner — groupes d'exécution
# ═══════════════════════════════════════════════════════════════

class TestBuildExecutionGroups:

    def _make_runner(self, steps_data):
        steps = [WorkflowStep(**s) for s in steps_data]
        wf = WorkflowDef(name="wf", steps=steps)
        return WorkflowRunner(wf)

    def test_sequential_groups(self):
        runner = self._make_runner([
            {"name": "a", "type": "job", "job": "./j", "depends_on": []},
            {"name": "b", "type": "job", "job": "./j", "depends_on": ["a"]},
            {"name": "c", "type": "job", "job": "./j", "depends_on": ["b"]},
        ])
        groups = runner._build_execution_groups()
        assert len(groups) == 3
        assert groups[0][0].name == "a"
        assert groups[1][0].name == "b"
        assert groups[2][0].name == "c"

    def test_parallel_group(self):
        runner = self._make_runner([
            {"name": "extract", "type": "job", "job": "./j", "depends_on": []},
            {"name": "t_a", "type": "job", "job": "./j", "depends_on": ["extract"]},
            {"name": "t_b", "type": "job", "job": "./j", "depends_on": ["extract"]},
            {"name": "load", "type": "job", "job": "./j", "depends_on": ["t_a", "t_b"]},
        ])
        groups = runner._build_execution_groups()
        assert len(groups) == 3
        parallel_names = {s.name for s in groups[1]}
        assert parallel_names == {"t_a", "t_b"}
        assert groups[2][0].name == "load"

    def test_cycle_raises(self):
        runner = self._make_runner([
            {"name": "a", "type": "job", "job": "./j", "depends_on": ["b"]},
            {"name": "b", "type": "job", "job": "./j", "depends_on": ["a"]},
        ])
        with pytest.raises(ValueError, match="[Cc]ycle"):
            runner._build_execution_groups()

    def test_unknown_dep_raises(self):
        runner = self._make_runner([
            {"name": "a", "type": "job", "job": "./j", "depends_on": ["ghost"]},
        ])
        with pytest.raises(ValueError):
            runner._build_execution_groups()


# ═══════════════════════════════════════════════════════════════
# 4. Runner — exécution réelle avec jobs CSV
# ═══════════════════════════════════════════════════════════════

class TestRunnerExecution:

    def test_sequential_success(self, tmp_path):
        """Workflow séquentiel : job_a → job_b, tous deux CSV valides."""
        job_a = make_job_dir(tmp_path, "job_a")
        job_b = make_job_dir(tmp_path, "job_b")

        p = write_workflow(tmp_path, f"""\
            workflow:
              name: seq
              steps:
                - name: job_a
                  type: job
                  job: '{job_a}'
                  depends_on: []
                  on_failure: fail
                - name: job_b
                  type: job
                  job: '{job_b}'
                  depends_on: [job_a]
                  on_failure: fail
        """)
        wf = load_workflow(p)
        result = WorkflowRunner(wf, base_dir=tmp_path).run()
        assert result.success is True
        assert len(result.steps) == 2
        assert all(s.success for s in result.steps)

    def test_action_log_success(self, tmp_path):
        """Action log passe sans erreur."""
        p = write_workflow(tmp_path, """\
            workflow:
              name: log_wf
              steps:
                - name: notify
                  type: action
                  action: log
                  params:
                    message: "Test log action"
                  depends_on: []
                  on_failure: fail
        """)
        wf = load_workflow(p)
        result = WorkflowRunner(wf, base_dir=tmp_path).run()
        assert result.success is True

    def test_on_failure_fail_stops_workflow(self, tmp_path):
        """on_failure=fail : le workflow s'arrête et le dépendant est skippé."""
        good_job = make_job_dir(tmp_path, "good")
        bad_wf = write_workflow(tmp_path, """\
            workflow:
              name: fail_wf
              steps:
                - name: bad_step
                  type: job
                  job: "/nonexistent/path"
                  depends_on: []
                  on_failure: fail
                - name: downstream
                  type: job
                  job: '{good_job}'
                  depends_on: [bad_step]
                  on_failure: fail
        """.format(good_job=good_job))
        wf = load_workflow(bad_wf)
        result = WorkflowRunner(wf, base_dir=tmp_path).run()
        assert result.success is False
        bad_sr = next(s for s in result.steps if s.step_name == "bad_step")
        assert bad_sr.success is False
        # downstream ne doit PAS apparaître (skippé → non exécuté)
        downstream_names = [s.step_name for s in result.steps]
        assert "downstream" not in downstream_names

    def test_on_failure_skip_continues(self, tmp_path):
        """on_failure=skip : le workflow continue malgré l'échec."""
        good_job = make_job_dir(tmp_path, "good")
        p = write_workflow(tmp_path, """\
            workflow:
              name: skip_wf
              steps:
                - name: bad_step
                  type: job
                  job: "/nonexistent/path"
                  depends_on: []
                  on_failure: skip
                - name: independent
                  type: action
                  action: log
                  params:
                    message: "independent step"
                  depends_on: []
                  on_failure: fail
        """)
        wf = load_workflow(p)
        result = WorkflowRunner(wf, base_dir=tmp_path).run()
        # independent doit avoir tourné
        ind = next((s for s in result.steps if s.step_name == "independent"), None)
        assert ind is not None
        assert ind.success is True

    def test_on_failure_continue(self, tmp_path):
        """on_failure=continue : workflow continue, résultat final non-success."""
        good_job = make_job_dir(tmp_path, "good")
        p = write_workflow(tmp_path, f"""\
            workflow:
              name: cont_wf
              steps:
                - name: failing
                  type: job
                  job: "/nonexistent/path"
                  depends_on: []
                  on_failure: continue
                - name: after
                  type: action
                  action: log
                  params:
                    message: "after failing"
                  depends_on: [failing]
                  on_failure: fail
        """)
        wf = load_workflow(p)
        result = WorkflowRunner(wf, base_dir=tmp_path).run()
        # "after" dépend de "failing" mais failing a on_failure=continue
        # donc after est dans le groupe suivant, mais failing a échoué
        # Le workflow est non-success global
        failing_sr = next((s for s in result.steps if s.step_name == "failing"), None)
        assert failing_sr is not None
        assert failing_sr.success is False

    def test_workflow_result_to_dict(self, tmp_path):
        """WorkflowResult.to_dict() retourne la structure attendue."""
        p = write_workflow(tmp_path, """\
            workflow:
              name: dict_wf
              steps:
                - name: s
                  type: action
                  action: log
                  params: {message: "hi"}
                  depends_on: []
        """)
        wf = load_workflow(p)
        result = WorkflowRunner(wf, base_dir=tmp_path).run()
        d = result.to_dict()
        assert d["workflow_name"] == "dict_wf"
        assert isinstance(d["steps"], list)
        assert d["steps"][0]["step_name"] == "s"

    def test_parallel_execution(self, tmp_path):
        """Fan-out : deux steps indépendants s'exécutent et finissent tous les deux."""
        job_a = make_job_dir(tmp_path, "job_a")
        job_b = make_job_dir(tmp_path, "job_b")
        p = write_workflow(tmp_path, f"""\
            workflow:
              name: par_wf
              steps:
                - name: branch_a
                  type: job
                  job: '{job_a}'
                  depends_on: []
                  on_failure: fail
                - name: branch_b
                  type: job
                  job: '{job_b}'
                  depends_on: []
                  on_failure: fail
        """)
        wf = load_workflow(p)
        result = WorkflowRunner(wf, base_dir=tmp_path).run()
        assert result.success is True
        names = {s.step_name for s in result.steps}
        assert names == {"branch_a", "branch_b"}

    def test_unknown_action_is_noop(self, tmp_path):
        """Une action inconnue est traitée comme noop (warning, success=True)."""
        p = write_workflow(tmp_path, """\
            workflow:
              name: noop_wf
              steps:
                - name: mystery
                  type: action
                  action: unknown_action_xyz
                  depends_on: []
                  on_failure: fail
        """)
        wf = load_workflow(p)
        result = WorkflowRunner(wf, base_dir=tmp_path).run()
        sr = result.steps[0]
        assert sr.success is True


# ═══════════════════════════════════════════════════════════════
# 5. CLI — hdrctl workflow
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def runner():
    return CliRunner()


class TestCLIWorkflowValidate:

    def test_valid_workflow(self, runner, tmp_path):
        p = write_workflow(tmp_path, SIMPLE_WF)
        result = runner.invoke(cli, ["workflow", "validate", str(p)])
        assert result.exit_code == 0

    def test_invalid_workflow_cycle(self, runner, tmp_path):
        p = write_workflow(tmp_path, """\
            workflow:
              name: bad
              steps:
                - name: a
                  type: job
                  job: ./j
                  depends_on: [b]
                - name: b
                  type: job
                  job: ./j
                  depends_on: [a]
        """)
        result = runner.invoke(cli, ["workflow", "validate", str(p)])
        assert result.exit_code != 0

    def test_missing_file(self, runner, tmp_path):
        result = runner.invoke(cli, ["workflow", "validate", str(tmp_path / "ghost.yaml")])
        assert result.exit_code != 0


class TestCLIWorkflowList:

    def test_list_finds_workflows(self, runner, tmp_path):
        write_workflow(tmp_path, SIMPLE_WF)
        result = runner.invoke(cli, ["workflow", "list", str(tmp_path)])
        assert result.exit_code == 0
        assert "test_wf" in result.output

    def test_list_empty_dir(self, runner, tmp_path):
        result = runner.invoke(cli, ["workflow", "list", str(tmp_path)])
        assert result.exit_code == 0

    def test_list_missing_dir(self, runner, tmp_path):
        result = runner.invoke(cli, ["workflow", "list", str(tmp_path / "ghost")])
        assert result.exit_code != 0


class TestCLIWorkflowRun:

    def test_run_with_log_action(self, runner, tmp_path):
        """Workflow avec une seule action log — doit passer."""
        p = write_workflow(tmp_path, """\
            workflow:
              name: cli_run_wf
              steps:
                - name: notify
                  type: action
                  action: log
                  params:
                    message: "CLI run test"
                  depends_on: []
                  on_failure: fail
        """)
        result = runner.invoke(cli, ["workflow", "run", str(p)])
        assert result.exit_code == 0
        assert "notify" in result.output

    def test_run_missing_file(self, runner, tmp_path):
        result = runner.invoke(cli, ["workflow", "run", str(tmp_path / "ghost.yaml")])
        assert result.exit_code != 0

    def test_run_failing_workflow_exits_nonzero(self, runner, tmp_path):
        p = write_workflow(tmp_path, """\
            workflow:
              name: fail_wf
              steps:
                - name: bad
                  type: job
                  job: "/nonexistent"
                  depends_on: []
                  on_failure: fail
        """)
        result = runner.invoke(cli, ["workflow", "run", str(p)])
        assert result.exit_code != 0


class TestCLIWorkflowInit:
    """workflow init écrit dans le répertoire courant -> toujours exécuter
    dans tmp_path (monkeypatch.chdir) pour ne pas polluer le repo."""

    def test_init_basic(self, runner, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(cli, ["workflow", "init", "my_wf", "--force"], catch_exceptions=False)
        # Doit créer my_wf.yaml dans le répertoire courant ou indiquer le chemin
        assert result.exit_code == 0

    def test_init_parallel_template(self, runner, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(
            cli,
            ["workflow", "init", "par_wf", "--template", "parallel", "--force"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0

    def test_init_scheduled_template(self, runner, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(
            cli,
            ["workflow", "init", "sched_wf", "--template", "scheduled", "--force"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
