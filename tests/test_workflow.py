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

    def test_unknown_action_is_rejected_at_load(self, tmp_path):
        """Une action inconnue est refusée au chargement, jamais exécutée."""
        p = write_workflow(tmp_path, """\
            workflow:
              name: typo_wf
              steps:
                - name: mystery
                  type: action
                  action: unknown_action_xyz
        """)
        with pytest.raises(ValueError, match="unknown action 'unknown_action_xyz'"):
            load_workflow(p)

    def test_unknown_action_suggests_closest(self, tmp_path):
        """Une faute de frappe reçoit une suggestion."""
        with pytest.raises(ValueError, match="did you mean 'powershell'"):
            WorkflowStep(name="s", type="action", action="powershel")

    def test_unknown_action_fails_if_validation_bypassed(self, tmp_path):
        """Défense en profondeur : un step construit sans validation échoue."""
        step = WorkflowStep.model_construct(
            name="mystery", type="action", action="telegram", params=None,
            depends_on=[], on_failure="fail", enabled=True, retry=None, when=None,
        )
        wf = WorkflowDef.model_construct(
            version="1.0", name="bypass", description=None,
            trigger=Trigger(), steps=[step],
        )
        result = WorkflowRunner(wf, base_dir=tmp_path).run()
        assert result.success is False
        assert result.steps[0].success is False
        assert "Unknown action 'telegram'" in result.steps[0].error

    def test_misspelled_step_key_is_rejected(self):
        """`depend_on` serait sinon ignoré : le step tournerait sans sa dépendance."""
        with pytest.raises(ValueError, match="unknown key 'depend_on' — did you mean 'depends_on'"):
            WorkflowStep(name="b", type="action", action="log", depend_on=["a"])

    def test_misspelled_param_is_rejected(self):
        with pytest.raises(ValueError, match="unknown parameter 'mesage' .* did you mean 'message'"):
            WorkflowStep(name="b", type="action", action="log", params={"mesage": "hi"})

    def test_missing_required_param_is_rejected(self):
        with pytest.raises(ValueError, match="action 'bash' requires parameter 'command'"):
            WorkflowStep(name="b", type="action", action="bash", params={})

    def test_blank_required_param_is_rejected(self):
        with pytest.raises(ValueError, match="requires parameter 'url'"):
            WorkflowStep(name="h", type="action", action="webhook", params={"url": "  "})

    def test_templated_required_param_is_accepted(self):
        WorkflowStep(name="h", type="action", action="webhook",
                     params={"url": "{{ param:hook_url }}"})

    def test_misspelled_retry_and_trigger_keys_are_rejected(self):
        with pytest.raises(ValueError, match="retry: unknown key 'retries'"):
            WorkflowStep(name="a", type="action", action="log", retry={"retries": 3})
        with pytest.raises(ValueError, match="trigger: unknown key 'cronn'"):
            Trigger(type="manual", cronn="0 2 * * *")

    def test_field_of_the_other_step_type_is_rejected(self):
        with pytest.raises(ValueError, match="apply to type=action, not type=job"):
            WorkflowStep(name="j", type="job", job="./j", action="log")
        with pytest.raises(ValueError, match="applies to type=job, not type=action"):
            WorkflowStep(name="a", type="action", action="log", job="./j")

    def test_misplaced_top_level_key_is_rejected(self, tmp_path):
        p = write_workflow(tmp_path, """\
            workflow:
              name: wf
              steps:
                - name: a
                  type: action
                  action: log
            trigger:
              type: schedule
              cron: "0 2 * * *"
        """)
        with pytest.raises(ValueError, match="top level: unknown key 'trigger'"):
            load_workflow(p)

    def test_webhook_sends_headers_and_text_body(self, tmp_path):
        """Studio saisit headers et body en texte JSON : les headers étaient
        ignorés et le body ré-encodé en chaîne JSON."""
        import json, threading
        from http.server import BaseHTTPRequestHandler, HTTPServer
        seen = {}

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                seen["auth"] = self.headers.get("Authorization")
                seen["body"] = self.rfile.read(int(self.headers["Content-Length"])).decode()
                self.send_response(204); self.end_headers()
            def log_message(self, *a):
                pass

        srv = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.handle_request, daemon=True).start()
        wf = WorkflowDef(name="hook", steps=[WorkflowStep(
            name="h", type="action", action="webhook", params={
                "url": f"http://127.0.0.1:{srv.server_port}/",
                "headers": '{"Authorization": "Bearer t0k"}',
                "body": '{"ok": true}',
            })])
        result = WorkflowRunner(wf, base_dir=tmp_path).run()
        srv.server_close()
        assert result.success, result.error
        assert seen["auth"] == "Bearer t0k"
        assert json.loads(seen["body"]) == {"ok": True}

    def test_known_actions_match_runner_handlers(self):
        """WORKFLOW_ACTIONS et la table action_handlers du runner ne divergent pas."""
        import sys
        tools = Path(__file__).resolve().parents[1] / "tools"
        sys.path.insert(0, str(tools))
        try:
            from spec_export import discover_actions
        finally:
            sys.path.remove(str(tools))
        from hydra_etl.workflow.models import WORKFLOW_ACTIONS
        assert set(discover_actions()) == set(WORKFLOW_ACTIONS)

    def test_declared_params_match_what_the_runner_reads(self):
        """Chaque params.get('x') du runner est déclaré dans ACTION_PARAMS, et
        inversement : un paramètre déclaré mais jamais lu serait accepté puis
        ignoré en silence."""
        import ast
        from hydra_etl.workflow.models import ACTION_PARAMS
        runner_py = Path(__file__).resolve().parents[1] / "hydra_etl" / "workflow" / "runner.py"
        tree = ast.parse(runner_py.read_text(encoding="utf-8"))
        handler_of = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "action_handlers" for t in node.targets
            ):
                for k, v in zip(node.value.keys, node.value.values):
                    handler_of[k.value] = v.attr
        read_by = {}
        for fn in ast.walk(tree):
            if isinstance(fn, ast.FunctionDef) and fn.name.startswith("_action_"):
                keys = set()
                for call in ast.walk(fn):
                    if (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                            and call.func.attr == "get" and isinstance(call.func.value, ast.Name)
                            and call.func.value.id == "params" and call.args
                            and isinstance(call.args[0], ast.Constant)):
                        keys.add(call.args[0].value)
                    if (isinstance(call, ast.Subscript) and isinstance(call.value, ast.Name)
                            and call.value.id == "params" and isinstance(call.slice, ast.Constant)):
                        keys.add(call.slice.value)
                read_by[fn.name] = keys
        for action, (required, optional) in ACTION_PARAMS.items():
            assert read_by[handler_of[action]] == set(required | optional), action

    def test_declared_params_cover_studio_fields(self):
        """Tout champ proposé par Studio doit être accepté, sinon un workflow
        dessiné dans Studio serait refusé au chargement."""
        import re
        from hydra_etl.workflow.models import ACTION_PARAMS
        tsx = (Path(__file__).resolve().parents[1] / "studio" / "src" / "components"
               / "canvas" / "NodeConfigDialog.tsx")
        if not tsx.exists():
            pytest.skip("sources Studio absentes")
        text = tsx.read_text(encoding="utf-8")
        for action, (required, optional) in ACTION_PARAMS.items():
            m = re.search(rf"^\s*action_{action}: \[(.*?)^\s*\],", text, re.S | re.M)
            if not m:
                continue
            fields = set(re.findall(r"key: '([a-z_]+)'", m.group(1)))
            assert fields <= set(required | optional), (action, fields - set(required | optional))


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

    def test_misspelled_action_fails_validation(self, runner, tmp_path):
        p = write_workflow(tmp_path, """\
            workflow:
              name: typo
              steps:
                - name: backup
                  type: action
                  action: powersheII
                  params:
                    command: echo hi
        """)
        result = runner.invoke(cli, ["workflow", "validate", str(p)])
        assert result.exit_code != 0
        assert "powersheII" in result.output

    def test_misspelled_action_does_not_run(self, runner, tmp_path):
        p = write_workflow(tmp_path, """\
            workflow:
              name: typo
              steps:
                - name: backup
                  type: action
                  action: powersheII
                  params:
                    command: echo hi
        """)
        result = runner.invoke(cli, ["workflow", "run", str(p)])
        assert result.exit_code == 1
        assert "did you mean 'powershell'" in result.output
        assert not isinstance(result.exception, ValueError)  # pas de trace Python

    @pytest.mark.skipif(__import__("sys").platform == "win32", reason="action bash")
    def test_run_lists_steps_that_never_ran(self, runner, tmp_path):
        """Un échec arrête le run : les steps non atteints sont affichés comme sautés."""
        p = write_workflow(tmp_path, """\
            workflow:
              name: chain
              steps:
                - name: fetch
                  type: action
                  action: bash
                  params:
                    command: exit 1
                - name: clean
                  type: action
                  action: log
                  depends_on: [fetch]
                  params:
                    message: never
        """)
        result = runner.invoke(cli, ["workflow", "run", str(p)])
        assert result.exit_code == 1
        assert "Step 'clean' skipped" in result.output
        assert "exited with code 1" in result.output


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
