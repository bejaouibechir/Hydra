"""hdrctl env | param | secret (0.18, phase B)."""
from pathlib import Path

import yaml
from click.testing import CliRunner

from hydra_etl.cli.hdrctl import cli
from hydra_etl.internal.config.loader import global_env_file, hydra_home


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / ".hydra").mkdir(parents=True)
    (root / ".hydra" / "project.json").write_text('{"name": "p"}', encoding="utf-8")
    return root


def _run(*args, input=None):
    r = CliRunner().invoke(cli, list(args), input=input, catch_exceptions=False)
    return r


def test_env_create_set_show_unset(tmp_path):
    root = _project(tmp_path)
    r = _run("env", "create", "prod", "--project", str(root))
    assert r.exit_code == 0, r.output
    assert global_env_file("prod").is_file()
    assert (root / "environments" / "prod.yaml").is_file()
    assert _run("env", "set", "DB_HOST", "db.prod", "--env", "prod").exit_code == 0
    assert _run("env", "set", "LOG", "a b ").exit_code == 0
    r = _run("env", "show", "prod")
    assert "DB_HOST" in r.output and "db.prod" in r.output
    from hydra_etl.internal.config.loader import parse_env_file
    assert parse_env_file(global_env_file(None))["LOG"] == "a b "
    assert _run("env", "unset", "DB_HOST", "--env", "prod").exit_code == 0
    assert _run("env", "unset", "DB_HOST", "--env", "prod").exit_code == 1


def test_env_create_twice_fails_and_bad_name(tmp_path):
    assert _run("env", "create", "dev").exit_code == 0
    assert _run("env", "create", "dev").exit_code == 1
    assert _run("env", "create", "bad name").exit_code == 1
    assert _run("env", "set", "1BAD", "x").exit_code == 1


def test_env_rename_and_delete_with_backup(tmp_path):
    root = _project(tmp_path)
    p = str(root)
    _run("env", "create", "staging", "--project", p)
    _run("env", "set", "A", "1", "--env", "staging")
    _run("param", "set", "x", "2", "--env", "staging", "--project", p)
    _run("secret", "set", "S", "--env", "staging", "--stdin", "--project", p, input="v\n")
    r = _run("env", "rename", "staging", "qa", "--project", p)
    assert r.exit_code == 0, r.output
    assert global_env_file("qa").is_file() and not global_env_file("staging").exists()
    assert (root / "environments" / "qa.yaml").is_file()
    assert (root / ".hydra" / "secrets.qa").is_file()
    r = _run("env", "delete", "qa", "-y", "--project", p)
    assert r.exit_code == 0, r.output
    assert not (root / ".hydra" / "secrets.qa").exists()
    backups = list((hydra_home() / "_backups").glob("*-delete-qa"))
    assert backups and (backups[0] / "secrets.qa").is_file()


def test_env_list(tmp_path):
    root = _project(tmp_path)
    _run("env", "create", "dev", "--project", str(root))
    r = _run("env", "list", "--project", str(root))
    assert r.exit_code == 0 and "dev" in r.output


def test_param_set_list_unset(tmp_path):
    root = _project(tmp_path)
    p = str(root)
    assert _run("param", "set", "batch", "500", "--type", "int", "--project", p).exit_code == 0
    assert _run("param", "set", "batch", "5000", "--env", "prod", "--project", p).exit_code == 0
    assert _run("param", "set", "batch", "abc", "--env", "dev", "--project", p).exit_code == 1
    decl = yaml.safe_load((root / "parameters.yaml").read_text())["parameters"]["batch"]
    assert decl == {"type": "int", "default": 500}
    assert yaml.safe_load((root / "environments" / "prod.yaml").read_text()) == {"parameters": {"batch": 5000}}
    r = _run("param", "list", "--project", p)
    assert "batch" in r.output and "5000" in r.output
    assert _run("param", "unset", "batch", "--env", "prod", "--project", p).exit_code == 0
    assert yaml.safe_load((root / "environments" / "prod.yaml").read_text()) == {"parameters": {}}
    assert _run("param", "unset", "batch", "--project", p).exit_code == 0
    assert _run("param", "unset", "batch", "--project", p).exit_code == 1


def test_param_keeps_other_keys(tmp_path):
    root = _project(tmp_path)
    (root / "parameters.yaml").write_text("version: '1'\nparameters:\n  a: {type: string, default: x}\n")
    _run("param", "set", "b", "true", "--project", str(root))
    data = yaml.safe_load((root / "parameters.yaml").read_text())
    assert data["version"] == "1"
    assert data["parameters"]["b"] == {"type": "bool", "default": True}


def test_secret_set_list_delete_never_prints_value(tmp_path):
    root = _project(tmp_path)
    p = str(root)
    r = _run("secret", "set", "DB_PW", "--project", p, input="s3cr3t-value\ns3cr3t-value\n")
    assert r.exit_code == 0, r.output
    _run("secret", "set", "DB_PW", "--env", "prod", "--stdin", "--project", p, input="prod-value\n")
    r = _run("secret", "list", "--env", "prod", "--project", p)
    assert "DB_PW" in r.output and "prod" in r.output
    assert "s3cr3t-value" not in r.output and "prod-value" not in r.output
    from hydra_etl.internal.config.secrets import project_secrets
    assert project_secrets(root, env="prod")["DB_PW"] == "prod-value"
    assert project_secrets(root)["DB_PW"] == "s3cr3t-value"
    assert _run("secret", "delete", "DB_PW", "--env", "prod", "--project", p).exit_code == 0
    assert _run("secret", "delete", "DB_PW", "--env", "prod", "--project", p).exit_code == 1


def test_secret_empty_value_refused(tmp_path):
    root = _project(tmp_path)
    r = _run("secret", "set", "X", "--stdin", "--project", str(root), input="\n")
    assert r.exit_code == 1


def test_job_run_reads_project_root_env(tmp_path, monkeypatch):
    """hdrctl run jobs/x : le .env à la racine du projet est lu."""
    import os
    root = _project(tmp_path)
    (root / ".env").write_text("ROOT_ONLY_VAR=from-root\n")
    job = root / "jobs" / "j"
    job.mkdir(parents=True)
    monkeypatch.delenv("ROOT_ONLY_VAR", raising=False)
    from hydra_etl.internal.runner.executor import JobExecutor
    try:
        JobExecutor(job)
    except Exception:
        pass                                   # job vide : seule la couche .env compte
    assert os.environ.get("ROOT_ONLY_VAR") == "from-root"
    monkeypatch.delenv("ROOT_ONLY_VAR", raising=False)
