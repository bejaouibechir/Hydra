"""Environnements 0.18 : variables globales (~/.hydra/env, env.<env>), secrets
par environnement (.hydra/secrets.<env>, sops.file avec {env}), --env-file,
--env sur `workflow run`."""
from __future__ import annotations

import json
import os
import subprocess
import textwrap
from pathlib import Path

import pytest
from click.testing import CliRunner

from hydra_etl.cli.hdrctl import cli
from hydra_etl.internal.config import loader
from hydra_etl.internal.config.secrets import SecretResolutionError, SecretResolver, project_secrets


@pytest.fixture
def home():
    return loader.hydra_home()


@pytest.fixture
def runner():
    return CliRunner(env={"HYDRA_LANG": "en"})


@pytest.fixture
def proj(tmp_path, runner):
    root = tmp_path / "proj"
    assert runner.invoke(cli, ["init", str(root), "-q"]).exit_code == 0
    return root


def _write(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(text), encoding="utf-8")
    return p


# ── Variables globales ──────────────────────────────────────────────────────
def test_global_env_common_then_environment(home, monkeypatch):
    monkeypatch.delenv("HX_A", raising=False)
    monkeypatch.delenv("HX_B", raising=False)
    _write(home / "env", "HX_A=common\n")
    _write(home / "env.prod", "HX_A=prod\nHX_B=only-prod\n")
    loader.apply_global_env("prod")
    assert os.environ["HX_A"] == "prod" and os.environ["HX_B"] == "only-prod"
    # changement d'environnement : la variable propre à prod disparaît
    loader.apply_global_env("dev")
    assert os.environ["HX_A"] == "common" and "HX_B" not in os.environ
    loader.restore_global_env()
    assert "HX_A" not in os.environ


def test_global_env_restores_original_values(home, monkeypatch):
    monkeypatch.setenv("HX_C", "from-shell")
    _write(home / "env.prod", "HX_C=from-file\n")
    loader.apply_global_env("prod")
    assert os.environ["HX_C"] == "from-file"           # un fichier l'emporte, comme les .env
    loader.apply_global_env(None)
    assert os.environ["HX_C"] == "from-shell"


def test_global_env_names_and_validation(home):
    _write(home / "env.prod", "A=1\n")
    _write(home / "env.dev", "A=1\n")
    assert loader.global_env_names() == ["dev", "prod"]
    with pytest.raises(ValueError, match="invalid environment name"):
        loader.global_env_file("../etc")


# ── Job : ordre des couches ─────────────────────────────────────────────────
def _job(root: Path, path_expr: str) -> Path:
    job = root / "jobs" / "j"
    _write(root / "data" / "in.csv", "id\n1\n2\n")
    _write(job / "sources.yaml", f"""\
        sources:
          src:
            type: csv
            extract:
              table: "{path_expr}"
        """)
    _write(job / "destinations.yaml", f"""\
        destinations:
          dst:
            type: csv
            load:
              table: "{(root / 'out.csv').as_posix()}"
              mode: replace
        """)
    _write(job / "pipeline.yaml", "pipeline:\n  from: src\n  to: dst\n")
    return job


def test_job_reads_global_variable_of_its_environment(tmp_path, home, monkeypatch):
    from hydra_etl.internal.runner.executor import JobExecutor
    monkeypatch.delenv("HX_DATA", raising=False)
    _write(home / "env.prod", f"HX_DATA={(tmp_path / 'data').as_posix()}\n")
    job = _job(tmp_path, "${ENV:HX_DATA}/in.csv")
    r = JobExecutor(job_dir=job, env="prod").run()
    assert r.success, r.error
    assert (tmp_path / "out.csv").read_text().splitlines() == ["id", "1", "2"]
    r = JobExecutor(job_dir=job, env="dev").run()          # pas de HX_DATA en dev
    assert not r.success and "HX_DATA" in r.error


def test_layer_order_global_project_job_envfile(tmp_path, home, monkeypatch):
    from hydra_etl.internal.runner.executor import JobExecutor
    for k in ("HX_L1", "HX_L2", "HX_L3"):
        monkeypatch.delenv(k, raising=False)
    _write(home / "env", "HX_L1=global\nHX_L2=global\nHX_L3=global\n")
    job = _job(tmp_path, "x.csv")
    _write(tmp_path / "jobs" / ".env", "HX_L2=project\nHX_L3=project\n")    # root_dir = parent du job
    _write(job / ".env", "HX_L3=job\n")
    JobExecutor(job_dir=job)
    assert (os.environ["HX_L1"], os.environ["HX_L2"], os.environ["HX_L3"]) == ("global", "project", "job")
    monkeypatch.setenv(loader.ENV_FILE_ENV, str(_write(tmp_path / "run.env", "HX_L3=env-file\n")))
    JobExecutor(job_dir=job)
    assert os.environ["HX_L3"] == "env-file"


def test_missing_env_file_is_an_error(tmp_path, monkeypatch):
    from hydra_etl.internal.runner.executor import JobExecutor
    monkeypatch.setenv(loader.ENV_FILE_ENV, str(tmp_path / "nope.env"))
    with pytest.raises(Exception, match="environment file not found"):
        JobExecutor(job_dir=_job(tmp_path, "x.csv"))


# ── Secrets par environnement ───────────────────────────────────────────────
def test_secrets_of_the_environment_win(proj):
    _write(proj / ".hydra" / "secrets", "db.password=dev-pass\napi.token=shared-tok\n")
    _write(proj / ".hydra" / "secrets.prod", "db.password=prod-pass\n")
    assert project_secrets(proj) == {"db.password": "dev-pass", "api.token": "shared-tok"}
    ps = project_secrets(proj, env="prod")
    assert ps == {"db.password": "prod-pass", "api.token": "shared-tok"}
    r = SecretResolver(secrets={}, fallback=ps)
    assert r.resolve("${SECRET:db.password}") == "prod-pass"


def test_secrets_environment_from_hydra_env(proj, monkeypatch):
    _write(proj / ".hydra" / "secrets.prod", "k=from-prod\n")
    monkeypatch.setenv("HYDRA_ENV", "prod")
    assert project_secrets(proj) == {"k": "from-prod"}


def test_sops_file_with_env_placeholder(proj):
    _write(proj / ".hydra" / "secrets.yaml", "provider: sops\nsops:\n  file: .hydra/secrets.{env}.sops.yaml\n")
    with pytest.raises(SecretResolutionError, match=r"uses \{env\} but no environment"):
        project_secrets(proj)
    ps = project_secrets(proj, env="prod")
    with pytest.raises(SecretResolutionError, match=r"secrets\.prod\.sops\.yaml"):
        ps.lookup("x")


def test_gitignore_covers_environment_secrets(proj):
    if subprocess.run(["git", "--version"], capture_output=True).returncode != 0:
        pytest.skip("git absent")
    subprocess.run(["git", "init", "-q"], cwd=proj, check=True)
    ignored = lambda f: subprocess.run(["git", "check-ignore", "-q", f], cwd=proj).returncode == 0  # noqa: E731
    assert ignored(".hydra/secrets") and ignored(".hydra/secrets.prod")
    assert not ignored(".hydra/secrets.yaml")
    assert not ignored(".hydra/secrets.prod.sops.yaml")


# ── CLI : workflow run --env / -P / --env-file ──────────────────────────────
def _say(root: Path, code: str) -> Path:
    log = root / "log.txt"
    _write(root / "workflows" / "s.yaml", f"""\
        workflow:
          name: s
          steps:
            - name: say
              type: action
              action: python
              params:
                script: {json.dumps(f"open(r'{log.as_posix()}', 'a').write({code} + chr(10))")}
        """)
    return log


def test_workflow_run_env_param_secret_and_global_variable(runner, proj, home, monkeypatch):
    monkeypatch.delenv("HX_REGION", raising=False)
    _write(proj / "parameters.yaml", "parameters:\n  country: {type: str, default: XX}\n")
    _write(proj / "environments" / "prod.yaml", "parameters:\n  country: BE\n")
    _write(proj / ".hydra" / "secrets.prod", "api.token=tok-prod-123\n")
    _write(home / "env.prod", "HX_REGION=eu-west\n")
    log = _say(proj, "'{{ param:country }}|${SECRET:api.token}|' + __import__('os').environ.get('HX_REGION', '-')")
    res = runner.invoke(cli, ["workflow", "run", "s", "--project", str(proj), "--env", "prod"])
    assert res.exit_code == 0, res.output
    assert log.read_text().splitlines() == ["BE|tok-prod-123|eu-west"]
    res = runner.invoke(cli, ["workflow", "run", "s", "--project", str(proj), "-P", "country=FR"])
    assert res.exit_code == 0, res.output
    assert log.read_text().splitlines()[-1].startswith("FR|")


def test_workflow_run_env_file(runner, proj, tmp_path, monkeypatch):
    monkeypatch.delenv("HX_FILEVAR", raising=False)
    log = _say(proj, "__import__('os').environ.get('HX_FILEVAR', '-')")
    ef = _write(tmp_path / "ci.env", "HX_FILEVAR=from-env-file\n")
    res = runner.invoke(cli, ["workflow", "run", "s", "--project", str(proj), "--env-file", str(ef)])
    assert res.exit_code == 0, res.output
    assert log.read_text().splitlines() == ["from-env-file"]
    res = runner.invoke(cli, ["workflow", "run", "s", "--project", str(proj), "--env-file", str(tmp_path / "x.env")])
    assert res.exit_code == 1 and "Environment file not found" in res.output
