"""Sortie des actions script dans `hdrctl workflow run`.

Le runner remonte le stdout/stderr d'une action python/bash/powershell dans
StepResult.output, et la CLI l'affiche sous la ligne du step. Les autres types
de steps (job, log, delay...) restent inchangés.
"""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest
from click.testing import CliRunner

from hydra_etl.cli.hdrctl import cli, _echo_step_output, _STEP_OUTPUT_MAX_LINES
from hydra_etl.workflow.models import StepResult
from hydra_etl.workflow.parser import load_workflow
from hydra_etl.workflow.runner import WorkflowRunner


@pytest.fixture
def runner():
    return CliRunner(env={"HYDRA_LANG": "en"})


def _workflow(tmp_path: Path, script: str, name: str = "say") -> Path:
    wf = tmp_path / "workflow.yaml"
    wf.write_text(textwrap.dedent(f"""\
        workflow:
          name: "t"
          trigger:
            type: manual
          steps:
            - name: "{name}"
              type: action
              action: python
              params:
                script: {script!r}
              depends_on: []
        """), encoding="utf-8")
    return wf


def test_runner_captures_python_action_output(tmp_path):
    wf = _workflow(tmp_path, "print('hello from the action')")
    result = WorkflowRunner(load_workflow(wf), base_dir=tmp_path).run()
    assert result.success
    assert result.steps[0].output == ["hello from the action"]


def test_output_is_empty_for_non_script_steps(tmp_path):
    wf = tmp_path / "workflow.yaml"
    wf.write_text(textwrap.dedent("""\
        workflow:
          name: "t"
          trigger:
            type: manual
          steps:
            - name: "note"
              type: action
              action: log
              params:
                message: "nothing to show"
              depends_on: []
        """), encoding="utf-8")
    result = WorkflowRunner(load_workflow(wf), base_dir=tmp_path).run()
    assert result.success
    assert result.steps[0].output == []


def test_cli_shows_the_output_under_the_step(runner, tmp_path):
    wf = _workflow(tmp_path, "print('42 rows written')")
    res = runner.invoke(cli, ["workflow", "run", str(wf)])
    assert res.exit_code == 0, res.output
    assert "Step 'say' OK" in res.output
    assert "42 rows written" in res.output


def test_long_output_is_truncated(runner, tmp_path):
    wf = _workflow(tmp_path, f"[print(i) for i in range({_STEP_OUTPUT_MAX_LINES + 5})]")
    res = runner.invoke(cli, ["workflow", "run", str(wf)])
    assert res.exit_code == 0, res.output
    assert "more line" in res.output  # compteur de lignes restantes
    assert f"\n     │ {_STEP_OUTPUT_MAX_LINES + 4}\n" not in res.output


def test_echo_step_output_tolerates_a_result_without_output(capsys):
    """Compatibilité : un StepResult construit sans le champ output."""
    _echo_step_output(StepResult(step_name="s", success=True, duration=0.0))
    assert capsys.readouterr().out == ""
