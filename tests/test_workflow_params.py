"""
Tests des actions runtime set_param / assign_param du Workflow Engine.

set_param    : crée un paramètre runtime au moment de l'exécution.
assign_param : affecte une valeur à un paramètre runtime déjà existant.

Les paramètres runtime sont partagés entre steps via WorkflowRunner.runtime_params.
"""
from __future__ import annotations

import pytest

from hydra_etl.workflow.models import WorkflowDef, WorkflowStep
from hydra_etl.workflow.runner import WorkflowRunner


def _wf(*steps: WorkflowStep) -> WorkflowDef:
    return WorkflowDef(name="params_wf", steps=list(steps))


def _step(result, name):
    """Retrouve un StepResult par nom dans la liste result.steps."""
    return next(s for s in result.steps if s.step_name == name)


def _set(name, value, dep=None, ptype=None, step_name=None):
    params = {"name": name, "value": value}
    if ptype is not None:
        params["type"] = ptype
    return WorkflowStep(
        name=step_name or f"set_{name}", type="action", action="set_param",
        params=params, depends_on=dep or [],
    )


def _assign(name, value, dep=None, ptype=None, step_name=None):
    params = {"name": name, "value": value}
    if ptype is not None:
        params["type"] = ptype
    return WorkflowStep(
        name=step_name or f"assign_{name}", type="action", action="assign_param",
        params=params, depends_on=dep or [],
    )


class TestSetParam:
    def test_creates_param(self):
        runner = WorkflowRunner(_wf(_set("x", 5, ptype="int")))
        result = runner.run()
        assert result.success
        assert runner.runtime_params["x"] == 5
        assert isinstance(runner.runtime_params["x"], int)

    def test_default_type_any_keeps_value(self):
        runner = WorkflowRunner(_wf(_set("label", "prod")))
        runner.run()
        assert runner.runtime_params["label"] == "prod"

    def test_set_on_existing_fails(self):
        runner = WorkflowRunner(_wf(
            _set("x", 1),
            _set("x", 2, dep=["set_x"], step_name="set_x_again"),
        ))
        result = runner.run()
        assert not result.success
        sr = _step(result, "set_x_again")
        assert not sr.success
        assert "existe déjà" in (sr.error or "")

    def test_missing_name_fails(self):
        runner = WorkflowRunner(_wf(WorkflowStep(
            name="bad", type="action", action="set_param",
            params={"value": 1},
        )))
        result = runner.run()
        assert not result.success

    def test_bad_type_coercion_fails(self):
        runner = WorkflowRunner(_wf(_set("n", "abc", ptype="int")))
        result = runner.run()
        assert not result.success
        assert "n" not in runner.runtime_params


class TestAssignParam:
    def test_assign_updates_existing(self):
        runner = WorkflowRunner(_wf(
            _set("x", 1, ptype="int"),
            _assign("x", 2, dep=["set_x"], ptype="int"),
        ))
        result = runner.run()
        assert result.success
        assert runner.runtime_params["x"] == 2

    def test_assign_missing_fails(self):
        runner = WorkflowRunner(_wf(_assign("ghost", 1)))
        result = runner.run()
        assert not result.success
        sr = _step(result, "assign_ghost")
        assert "n'existe pas" in (sr.error or "")

    def test_persists_across_steps(self):
        runner = WorkflowRunner(_wf(
            _set("counter", 10, ptype="int"),
            _assign("counter", 20, dep=["set_counter"], ptype="int",
                    step_name="bump"),
        ))
        runner.run()
        assert runner.runtime_params["counter"] == 20


class TestParamResolution:
    def test_placeholder_resolved_in_log(self):
        log = WorkflowStep(
            name="show", type="action", action="log",
            params={"message": "echo {{ param:me }}"},
            depends_on=["set_me"],
        )
        runner = WorkflowRunner(_wf(_set("me", "bechir", step_name="set_me"), log))
        result = runner.run()
        assert result.success
        sr = _step(result, "show")
        assert any("echo bechir" in line for line in sr.logs)

    def test_full_placeholder_preserves_type(self):
        copy = WorkflowStep(
            name="set_copy", type="action", action="set_param",
            params={"name": "copy", "value": "{{ param:n }}", "type": "int"},
            depends_on=["set_n"],
        )
        runner = WorkflowRunner(_wf(_set("n", 5, ptype="int", step_name="set_n"), copy))
        result = runner.run()
        assert result.success
        assert runner.runtime_params["copy"] == 5
        assert isinstance(runner.runtime_params["copy"], int)

    def test_unknown_param_fails(self):
        log = WorkflowStep(
            name="bad", type="action", action="log",
            params={"message": "{{ param:ghost }}"},
        )
        result = WorkflowRunner(_wf(log)).run()
        assert not result.success


class TestJobPropagation:
    def test_runtime_params_propagate_to_job(self, tmp_path):
        from unittest.mock import patch, MagicMock

        jobdir = tmp_path / "jobs" / "x"
        jobdir.mkdir(parents=True)
        job_step = WorkflowStep(name="j", type="job", job="./jobs/x",
                                depends_on=["set_p"])
        wf = _wf(_set("p", "v", step_name="set_p"), job_step)
        runner = WorkflowRunner(wf, base_dir=tmp_path)

        captured = {}
        fake_exec = MagicMock()
        fake_exec.run.return_value = MagicMock(
            success=True, rows_out=0, rows_in=0, error=None, duration=0.0)

        def factory(**kwargs):
            captured.update(kwargs)
            return fake_exec

        with patch("hydra_etl.internal.runner.executor.JobExecutor", side_effect=factory):
            result = runner.run()

        assert result.success
        assert captured.get("params", {}).get("p") == "v"


class TestEnvInjection:
    def test_bash_reads_param_as_env(self):
        import sys
        if sys.platform == "win32":
            import pytest as _pt; _pt.skip("bash indisponible sur Windows")
        bash = WorkflowStep(
            name="sh", type="action", action="bash",
            params={"command": 'echo "greeting=$greeting"'},
            depends_on=["set_g"],
        )
        runner = WorkflowRunner(_wf(_set("greeting", "hello", step_name="set_g"), bash))
        result = runner.run()
        assert result.success
        sr = _step(result, "sh")
        assert any("greeting=hello" in l for l in sr.logs)

    def test_env_vars_filtered_and_typed(self):
        runner = WorkflowRunner(_wf(_set("x", 1)))
        runner.runtime_params = {"ok_name": 5, "bad-name": "z", "flag": True, "none_v": None}
        env = runner._runtime_env_vars()
        assert env == {"ok_name": "5", "flag": "true"}


class TestJobPrecheck:
    def _mk_job(self, tmp_path, src_table, dst_table):
        j = tmp_path / "jobs" / "x"
        j.mkdir(parents=True)
        (j / "sources.yaml").write_text(
            f"sources:\n  s:\n    type: csv\n    connection: {{}}\n"
            f"    extract: {{ table: '{src_table}', batch_size: 1000 }}\n",
            encoding="utf-8")
        (j / "destinations.yaml").write_text(
            f"destinations:\n  d:\n    type: csv\n    connection: {{}}\n"
            f"    load: {{ table: '{dst_table}', mode: replace }}\n",
            encoding="utf-8")
        (j / "pipeline.yaml").write_text(
            "pipeline: { name: x, from: s, to: d }\n", encoding="utf-8")
        return j

    def test_empty_job_gets_clear_error(self, tmp_path):
        self._mk_job(tmp_path, "", "")
        wf = _wf(WorkflowStep(name="j", type="job", job="./jobs/x"))
        res = WorkflowRunner(wf, base_dir=tmp_path).run()
        assert not res.success
        err = _step(res, "j").error or ""
        assert "non configuré" in err
        assert "requiert une source et une destination" in err

    def test_placeholder_source_passes_precheck(self, tmp_path):
        j = self._mk_job(tmp_path, "{{ param:src }}", "out.csv")
        from hydra_etl.workflow.runner import WorkflowRunner as WR
        # le precheck ne doit PAS lever pour un placeholder non vide
        WR._precheck_job_configured(j, "j")


class TestProjectParams:
    def _mk_project(self, tmp_path):
        (tmp_path / "parameters.yaml").write_text(
            "parameters:\n  host_ip:\n    type: string\n    default: 127.0.0.1\n",
            encoding="utf-8")
        return tmp_path

    def test_action_resolves_project_param(self, tmp_path):
        self._mk_project(tmp_path)
        wf = _wf(WorkflowStep(name="show", type="action", action="log",
                              params={"message": "ip={{ param:host_ip }}"}))
        res = WorkflowRunner(wf, base_dir=tmp_path).run()
        assert res.success
        assert any("ip=127.0.0.1" in l for l in _step(res, "show").logs)

    def test_runtime_overrides_project(self, tmp_path):
        self._mk_project(tmp_path)
        wf = _wf(
            _set("host_ip", "10.0.0.9", step_name="ovr"),
            WorkflowStep(name="show", type="action", action="log",
                         params={"message": "ip={{ param:host_ip }}"},
                         depends_on=["ovr"]),
        )
        res = WorkflowRunner(wf, base_dir=tmp_path).run()
        assert res.success
        assert any("ip=10.0.0.9" in l for l in _step(res, "show").logs)

    def test_env_scoped_value(self, tmp_path):
        self._mk_project(tmp_path)
        envd = tmp_path / "environments"; envd.mkdir()
        (envd / "prod.yaml").write_text(
            "parameters:\n  host_ip: 192.168.1.50\n", encoding="utf-8")
        wf = _wf(WorkflowStep(name="show", type="action", action="log",
                              params={"message": "ip={{ param:host_ip }}"}))
        res = WorkflowRunner(wf, base_dir=tmp_path, env="prod").run()
        assert res.success
        assert any("ip=192.168.1.50" in l for l in _step(res, "show").logs)


class TestPythonAction:
    def test_inline_script_with_param(self, tmp_path):
        (tmp_path / "parameters.yaml").write_text(
            "parameters:\n  host_ip:\n    type: string\n    default: 127.0.0.1\n",
            encoding="utf-8")
        wf = _wf(WorkflowStep(name="p", type="action", action="python",
                              params={"script": 'print("{{ param:host_ip }}")'}))
        res = WorkflowRunner(wf, base_dir=tmp_path).run()
        assert res.success
        assert any("127.0.0.1" in l for l in _step(res, "p").logs)

    def test_env_var_injection(self):
        wf = _wf(
            _set("greet", "hola", step_name="s"),
            WorkflowStep(name="p", type="action", action="python",
                         params={"script": 'import os; print(os.environ["greet"])'},
                         depends_on=["s"]),
        )
        res = WorkflowRunner(wf).run()
        assert res.success
        assert any("hola" in l for l in _step(res, "p").logs)

    def test_missing_script_fails(self):
        wf = _wf(WorkflowStep(name="p", type="action", action="python", params={}))
        res = WorkflowRunner(wf).run()
        assert not res.success
        assert "requis" in (_step(res, "p").error or "")
