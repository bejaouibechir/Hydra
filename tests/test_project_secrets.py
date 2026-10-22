"""Secrets du projet : .hydra/secrets (name=value), lus par ${SECRET:name} dans
les jobs et les workflows. Une variable d'environnement l'emporte sur le
fichier ; --secrets-file / HYDRA_SECRETS_FILE désignent un fichier ailleurs."""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
from click.testing import CliRunner

from hydra_etl.cli.hdrctl import cli
from hydra_etl.internal.config.secrets import (
    SECRETS_FILE_ENV, SecretResolutionError, SecretResolver, parse_secrets_text,
    project_secrets, scaffold_secrets,
)


@pytest.fixture
def runner():
    return CliRunner(env={"HYDRA_LANG": "en"})


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in (SECRETS_FILE_ENV, "DB_PASSWORD", "IN_FILE"):
        monkeypatch.delenv(k, raising=False)


@pytest.fixture
def proj(tmp_path, runner):
    root = tmp_path / "proj"
    assert runner.invoke(cli, ["init", str(root), "-q"]).exit_code == 0
    return root


def _say_workflow(root: Path, text: str = "pw=${SECRET:db.password}") -> None:
    log = (root / "log.txt").as_posix()
    (root / "workflows" / "s.yaml").write_text(textwrap.dedent(f"""\
        workflow:
          name: s
          steps:
            - name: say
              type: action
              action: python
              params:
                script: {json.dumps(f"open(r'{log}', 'a').write('{text}' + chr(10))")}
        """), encoding="utf-8")
    (root / "workflows" / "thread.yaml").write_text(
        'thread:\n  - workflows:\n      - name: s\n', encoding="utf-8")


def _log(root: Path) -> list:
    f = root / "log.txt"
    return f.read_text(encoding="utf-8").splitlines() if f.exists() else []


# ── Format ────────────────────────────────────────────────────────────────────

def test_parse_secrets_text():
    text = '# comment\n\ndb.password = "a=b c"\nexport API_TOKEN=xyz\nk-1=\'q\'\nempty=\n'
    assert parse_secrets_text(text) == {"db.password": "a=b c", "API_TOKEN": "xyz", "k-1": "q", "empty": ""}


@pytest.mark.parametrize("line,fragment", [
    ("novalue", "line 2: expected name=value"),
    ("bad key=SUPERSECRET", "invalid secret name"),
])
def test_parse_errors_never_show_values(line, fragment):
    with pytest.raises(SecretResolutionError) as e:
        parse_secrets_text("ok=1\n" + line)
    assert fragment in str(e.value)
    assert "SUPERSECRET" not in str(e.value)


# ── Précédence ────────────────────────────────────────────────────────────────

def test_environment_wins_over_file(monkeypatch):
    r = SecretResolver(secrets={}, fallback={"db.password": "file"})
    assert r.resolve("${SECRET:db.password}") == "file"
    monkeypatch.setenv("DB_PASSWORD", "env")
    assert r.resolve("${SECRET:db.password}") == "env"
    assert SecretResolver(secrets={"db.password": "injected"}, fallback={}).resolve(
        "${SECRET:db.password}") == "injected"


def test_missing_secret_names_both_places():
    with pytest.raises(SecretResolutionError) as e:
        SecretResolver(secrets={}).resolve("${SECRET:db.password}")
    assert "DB_PASSWORD" in str(e.value) and ".hydra/secrets" in str(e.value)


def test_project_secrets_lookup(proj, tmp_path, monkeypatch):
    (proj / ".hydra" / "secrets").write_text("db.password=p\n", encoding="utf-8")
    assert project_secrets(proj / "jobs" / "job1") == {"db.password": "p"}
    assert project_secrets(tmp_path / "elsewhere") == {}
    other = tmp_path / "vault.secrets"
    other.write_text("db.password=v\n", encoding="utf-8")
    monkeypatch.setenv(SECRETS_FILE_ENV, str(other))
    assert project_secrets(proj) == {"db.password": "v"}
    monkeypatch.setenv(SECRETS_FILE_ENV, str(tmp_path / "missing"))
    with pytest.raises(SecretResolutionError, match="not found"):
        project_secrets(proj)


# ── Scaffold ──────────────────────────────────────────────────────────────────

def test_init_creates_commented_secrets_and_gitignore(proj):
    assert project_secrets(proj) == {}                     # modèle : rien que des commentaires
    gi = (proj / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".hydra/secrets" in gi and ".env" in gi
    assert not (proj / ".hydra" / "workflows").exists()    # créé par Studio au besoin


def test_scaffold_never_overwrites(tmp_path):
    (tmp_path / ".hydra").mkdir()
    (tmp_path / ".hydra" / "secrets").write_text("a=1\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("node_modules/\n.env\n", encoding="utf-8")
    assert scaffold_secrets(tmp_path) == [".gitignore"]
    assert (tmp_path / ".hydra" / "secrets").read_text(encoding="utf-8") == "a=1\n"
    lines = (tmp_path / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert lines[0] == "node_modules/" and lines.count(".env") == 1 and ".hydra/secrets" in lines
    assert scaffold_secrets(tmp_path) == []


def test_git_ignores_the_secrets_file(proj):
    import shutil, subprocess
    if shutil.which("git") is None:
        pytest.skip("git absent")
    subprocess.run(["git", "init", "-q"], cwd=proj, check=True)
    out = subprocess.run(["git", "check-ignore", ".hydra/secrets"], cwd=proj,
                         capture_output=True, text=True)
    assert out.returncode == 0


# ── Utilisation : workflows et jobs ───────────────────────────────────────────

def test_workflow_action_reads_project_secret(runner, proj, monkeypatch):
    (proj / ".hydra" / "secrets").write_text("db.password=from-file\n", encoding="utf-8")
    _say_workflow(proj)
    assert runner.invoke(cli, ["run", str(proj)]).exit_code == 0
    monkeypatch.setenv("DB_PASSWORD", "from-env")
    assert runner.invoke(cli, ["run", str(proj)]).exit_code == 0
    assert _log(proj) == ["pw=from-file", "pw=from-env"]


def test_secrets_file_option(runner, proj, tmp_path):
    other = tmp_path / "elsewhere.secrets"
    other.write_text("db.password=elsewhere\n", encoding="utf-8")
    _say_workflow(proj)
    res = runner.invoke(cli, ["run", str(proj), "--secrets-file", str(other)])
    assert res.exit_code == 0, res.output
    assert _log(proj) == ["pw=elsewhere"]
    res = runner.invoke(cli, ["run", str(proj), "--secrets-file", str(tmp_path / "nope")])
    assert res.exit_code == 1 and "Secrets file not found" in res.output


def test_missing_secret_fails_the_step(runner, proj):
    _say_workflow(proj)
    res = runner.invoke(cli, ["run", str(proj)])
    assert res.exit_code == 1
    assert "Missing secret: db.password" in res.output


def test_job_reads_project_secret(runner, proj):
    (proj / ".hydra" / "secrets").write_text("in.file=data/input.csv\n", encoding="utf-8")
    src = proj / "jobs" / "job1" / "sources.yaml"
    src.write_text(src.read_text(encoding="utf-8").replace("table: data/input.csv",
                                                          "table: ${SECRET:in.file}"), encoding="utf-8")
    assert "${SECRET:in.file}" in src.read_text(encoding="utf-8")
    res = runner.invoke(cli, ["run", str(proj / "jobs" / "job1")])
    assert res.exit_code == 0, res.output
    res = runner.invoke(cli, ["run", str(proj)])
    assert res.exit_code == 0, res.output


# ── Édition du fichier (Studio) ───────────────────────────────────────────────

def test_set_and_delete_secret_keep_comments(tmp_path):
    from hydra_etl.internal.config.secrets import delete_secret, load_secrets_file, set_secret
    f = tmp_path / ".hydra" / "secrets"
    set_secret(f, "db.password", "p1")                       # créé depuis le modèle commenté
    text = f.read_text(encoding="utf-8")
    assert text.startswith("# Project secrets") and text.rstrip().endswith("db.password=p1")
    set_secret(f, "api.token", "  spaced value ")
    set_secret(f, "db.password", "p2")                       # remplacé sur place
    set_secret(f, "q", '"quoted"')
    assert load_secrets_file(f) == {"db.password": "p2", "api.token": "  spaced value ", "q": '"quoted"'}
    assert [ln for ln in f.read_text(encoding="utf-8").splitlines() if ln.startswith("db.password=")] == ["db.password=p2"]
    assert delete_secret(f, "api.token") is True
    assert delete_secret(f, "api.token") is False
    assert "# Project secrets" in f.read_text(encoding="utf-8")
    with pytest.raises(SecretResolutionError):
        set_secret(f, "bad name", "x")
    with pytest.raises(SecretResolutionError):
        set_secret(f, "x", "a\nb")


def test_env_override(monkeypatch):
    from hydra_etl.internal.config.secrets import env_override
    assert env_override("db.password") is None
    monkeypatch.setenv("DB_PASSWORD", "x")
    assert env_override("db.password") == "DB_PASSWORD"


def test_gitignore_covers_studio_env_files(proj):
    import shutil, subprocess
    if shutil.which("git") is None:
        pytest.skip("git absent")
    subprocess.run(["git", "init", "-q"], cwd=proj, check=True)
    for f in (".env", ".env.prod", "jobs/job1/.env"):
        assert subprocess.run(["git", "check-ignore", "-q", f], cwd=proj).returncode == 0, f
    assert subprocess.run(["git", "check-ignore", "-q", "jobs/job1/.env.example"], cwd=proj).returncode == 1


# ── API /api/secrets ──────────────────────────────────────────────────────────

@pytest.fixture
def api_proj(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from hydra_etl.api import store
    monkeypatch.setattr(store, "WORKSPACE", tmp_path / "ws")
    monkeypatch.setattr(store, "_INDEX_FILE", tmp_path / "ws" / "index.json")
    (tmp_path / "ws").mkdir()
    proj = store.create_project("p", project_path=str(tmp_path))
    return proj, Path(proj.path)


def test_api_secrets_never_returns_values(api_proj, monkeypatch):
    from fastapi import HTTPException
    from hydra_etl.api.routers import secrets as r
    proj, root = api_proj
    out = r.list_secrets(project_id=proj.id)
    assert out.file == ".hydra/secrets" and out.exists and out.secrets == [] and not out.external
    out = r.put_secret(r.SecretSet(project_id=proj.id, name="db.password", value="TOPSECRET"))
    assert [s.name for s in out.secrets] == ["db.password"]
    assert "TOPSECRET" not in out.model_dump_json()
    assert project_secrets(root) == {"db.password": "TOPSECRET"}
    monkeypatch.setenv("DB_PASSWORD", "env")
    assert r.list_secrets(project_id=proj.id).secrets[0].overridden_by == "DB_PASSWORD"
    out = r.remove_secret("db.password", project_id=proj.id)
    assert out.secrets == []
    with pytest.raises(HTTPException) as e:
        r.remove_secret("db.password", project_id=proj.id)
    assert e.value.status_code == 404
    with pytest.raises(HTTPException) as e:
        r.put_secret(r.SecretSet(project_id=proj.id, name="bad name", value="x"))
    assert e.value.status_code == 422


def test_api_secrets_external_file(api_proj, tmp_path, monkeypatch):
    from hydra_etl.api.routers import secrets as r
    proj, root = api_proj
    ext = tmp_path / "vault" / "app.secrets"
    monkeypatch.setenv(SECRETS_FILE_ENV, str(ext))
    out = r.put_secret(r.SecretSet(project_id=proj.id, name="k", value="v"))
    assert out.external and out.file == str(ext)
    assert ext.read_text(encoding="utf-8").rstrip().endswith("k=v")
    assert "k=" not in (root / ".hydra" / "secrets").read_text(encoding="utf-8")
