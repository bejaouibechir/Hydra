"""validate : pipeline.from / pipeline.to cassés, et un total d'erreurs juste.

Avant : le nombre affiché ne comptait que les erreurs de schéma (« 0 error(s)
detected » avec une erreur à l'écran), l'ancien format `job: pipeline:` et un
`from` absent passaient, et `hdrctl run <projet> --dry-run` ne regardait pas
pipeline.yaml des jobs.
"""
import re

import pytest
from click.testing import CliRunner

from hydra_etl.cli.hdrctl import cli
from hydra_etl.workflow.jobcheck import pipeline_errors


@pytest.fixture
def proj(tmp_path):
    root = tmp_path / "p"
    assert CliRunner().invoke(cli, ["init", str(root), "-q"]).exit_code == 0
    return root


def _validate(job):
    r = CliRunner().invoke(cli, ["validate", str(job), "--lang", "en"])
    m = re.search(r"(\d+) error\(s\) detected", r.output)
    return r.exit_code, (int(m.group(1)) if m else 0), r.output


def _pipe(job, text):
    (job / "pipeline.yaml").write_text(text, encoding="utf-8")


def test_valid_job(proj):
    code, n, out = _validate(proj / "jobs" / "job1")
    assert code == 0 and "no errors" in out


def test_broken_from_is_counted(proj):
    job = proj / "jobs" / "job1"
    _pipe(job, "pipeline:\n  from: nope\n  to: dest_csv\n")
    code, n, out = _validate(job)
    assert code == 1 and n == 1
    assert "pipeline.from='nope' not found" in out


def test_broken_from_and_to(proj):
    job = proj / "jobs" / "job1"
    _pipe(job, "pipeline:\n  from: nope\n  to: nada\n")
    assert _validate(job)[:2] == (1, 2)


def test_legacy_nested_format_is_checked(proj):
    job = proj / "jobs" / "job1"
    _pipe(job, "job:\n  pipeline:\n    from: nope\n    to: dest_csv\n")
    code, n, out = _validate(job)
    assert code == 1 and n == 1


def test_missing_from_and_unknown_key(proj):
    job = proj / "jobs" / "job1"
    _pipe(job, "pipeline:\n  form: src_csv\n  to: dest_csv\n")
    code, n, out = _validate(job)
    assert code == 1 and n == 2
    assert "pipeline.from is missing" in out and "form" in out


def test_missing_section(proj):
    job = proj / "jobs" / "job1"
    _pipe(job, "from: src_csv\nto: dest_csv\n")
    code, n, out = _validate(job)
    assert code == 1 and n >= 1 and "'pipeline:' section missing" in out


def test_parameter_reference_is_not_an_error(proj):
    job = proj / "jobs" / "job1"
    _pipe(job, "pipeline:\n  from: ${src}\n  to: dest_csv\n")
    code, n, out = _validate(job)
    assert code == 0 and "resolved at run time" in out


def test_job_dry_run_uses_same_check(proj):
    job = proj / "jobs" / "job1"
    _pipe(job, "job:\n  pipeline:\n    from: nope\n    to: dest_csv\n")
    r = CliRunner().invoke(cli, ["run", str(job), "--dry-run", "--lang", "en"])
    assert r.exit_code != 0 and "pipeline.from='nope'" in r.output


def test_project_dry_run_catches_broken_job(proj):
    _pipe(proj / "jobs" / "job1", "pipeline:\n  from: nope\n  to: dest_csv\n")
    r = CliRunner().invoke(cli, ["run", str(proj), "--dry-run", "--lang", "en"])
    assert r.exit_code != 0
    assert "pipeline.from='nope' not found in sources.yaml" in r.output


def test_pipeline_errors_helper(proj):
    job = proj / "jobs" / "job1"
    assert pipeline_errors(job) == []
    _pipe(job, "pipeline:\n  from: src_csv\n  to: nada\n")
    assert pipeline_errors(job) == ["pipeline.to='nada' not found in destinations.yaml"]
