"""Secrets : masquage dans les logs / messages / résultats (plain | masked |
hidden), réglages .hydra/secrets.yaml, fournisseur SOPS (+ age)."""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest
from click.testing import CliRunner

from hydra_etl.cli.hdrctl import cli
from hydra_etl.internal.config import masking
from hydra_etl.internal.config.masking import (
    MASK, redact_lines, redact_text, register, resolve_visibility,
)
from hydra_etl.internal.config.secrets import (
    SECRETS_FILE_ENV, SecretResolutionError, SecretResolver, delete_secret,
    load_secrets_file, project_secrets, set_secret,
)

SECRET = "Sup3r-S3cret!value"


@pytest.fixture
def runner():
    return CliRunner(env={"HYDRA_LANG": "en"})


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in (SECRETS_FILE_ENV, "API_TOKEN", "DB_PASSWORD", masking.VISIBILITY_ENV,
              "SOPS_AGE_KEY_FILE"):
        monkeypatch.delenv(k, raising=False)


@pytest.fixture
def proj(tmp_path, runner):
    root = tmp_path / "proj"
    assert runner.invoke(cli, ["init", str(root), "-q"]).exit_code == 0
    return root


def _workflow(root: Path, script: str, *, fail: bool = False, extra: str = "") -> None:
    code = script + ("\nimport sys; sys.exit(3)" if fail else "")
    (root / "workflows" / "s.yaml").write_text(textwrap.dedent(f"""\
        workflow:
          name: s
          steps:
            - name: say
              type: action
              action: python
              params:
                script: {json.dumps(code)}
        """) + extra, encoding="utf-8")
    (root / "workflows" / "thread.yaml").write_text(
        'thread:\n  - workflows:\n      - name: s\n', encoding="utf-8")


def _run_wf(root: Path):
    from hydra_etl.workflow.parser import load_workflow
    from hydra_etl.workflow.runner import WorkflowRunner
    wf = load_workflow(str(root / "workflows" / "s.yaml"))
    return WorkflowRunner(wf, base_dir=root / "workflows", project_root=root).run()


def _all_text(result) -> str:
    parts = [result.error or ""]
    for s in result.steps:
        parts += [s.error or ""] + list(s.logs) + list(s.output)
    parts.append(json.dumps(result.rollback or {}))
    return "\n".join(parts)


# ── Unitaire ────────────────────────────────────────────────────────────────
def test_masked_replaces_every_form_of_the_value():
    register(SECRET, "masked")
    text = f"pw={SECRET} url=postgres://u:{SECRET.replace('!', '%21')}@h json=\"{SECRET}\""
    out = redact_text(text)
    assert SECRET not in out and "%21" not in out and out.count(MASK) == 3


def test_hidden_drops_the_lines_and_says_so():
    register(SECRET, "hidden")
    out = redact_lines(["a", f"x {SECRET}", f"y {SECRET}", "b"])
    assert out == ["a", "[2 line(s) hidden: they contain a secret]", "b"]
    assert redact_text(f"one\ntwo {SECRET}") == "one\n[1 line(s) hidden: they contain a secret]"


def test_plain_masks_nothing_but_warns(caplog):
    with caplog.at_level(logging.WARNING):
        register(SECRET, "plain")
    assert redact_text(SECRET) == SECRET
    assert "plain" in caplog.text and SECRET not in caplog.text


def test_short_values_are_not_masked_and_a_warning_says_so(caplog):
    with caplog.at_level(logging.WARNING):
        register("abc", "masked", name="tiny")
    assert redact_text("abc") == "abc"
    assert "'tiny'" in caplog.text and "abc" not in caplog.text.replace("'tiny'", "")


def test_multiline_value_masks_each_line():
    pem = "-----BEGIN KEY-----\nAAAABBBBCCCC\nDDDDEEEEFFFF\n-----END KEY-----"
    register(pem, "masked")
    assert "AAAABBBBCCCC" not in redact_text("leaked: AAAABBBBCCCC")


def test_strictest_visibility_wins():
    register(SECRET, "masked")
    register(SECRET, "hidden")
    assert redact_text(f"x {SECRET}") == "[1 line(s) hidden: they contain a secret]"


def test_logs_and_tracebacks_are_masked(caplog):
    register(SECRET, "masked")
    log = logging.getLogger("hydra_etl.internal.test")
    with caplog.at_level(logging.INFO):
        log.info("connecting with %s", SECRET)
        try:
            raise RuntimeError(f"login failed for {SECRET}")
        except RuntimeError:
            log.exception("boom")
    text = caplog.text + "".join(r.exc_text or "" for r in caplog.records)
    assert SECRET not in text and MASK in text


def test_visibility_precedence(monkeypatch):
    assert resolve_visibility(None) == "masked"
    assert resolve_visibility("hidden") == "hidden"
    monkeypatch.setenv(masking.VISIBILITY_ENV, "plain")
    assert resolve_visibility("hidden") == "plain"
    monkeypatch.setenv(masking.VISIBILITY_ENV, "loud")
    with pytest.raises(ValueError, match="plain, masked, hidden"):
        resolve_visibility(None)


def test_resolver_registers_env_secrets(monkeypatch):
    monkeypatch.setenv("API_TOKEN", SECRET)
    assert SecretResolver(secrets={}).resolve("${SECRET:api.token}") == SECRET
    assert redact_text(SECRET) == MASK


def test_redact_model_in_place():
    from pydantic import BaseModel

    class Run(BaseModel):
        error: str = ""
        steps: list = []

    register(SECRET, "masked")
    r = Run(error=f"e {SECRET}", steps=[{"logs": [f"l {SECRET}"], "n": 1}])
    assert masking.redact_model(r) is r
    assert SECRET not in r.model_dump_json()


# ── Réglages .hydra/secrets.yaml ────────────────────────────────────────────
def _settings(root: Path, text: str) -> None:
    (root / ".hydra" / "secrets.yaml").write_text(textwrap.dedent(text), encoding="utf-8")


def test_settings_visibility_from_project(proj):
    _settings(proj, "visibility: hidden\n")
    set_secret(proj / ".hydra" / "secrets", "db.password", SECRET)
    ps = project_secrets(proj)
    assert ps == {"db.password": SECRET} and ps.visibility == "hidden"
    # Toutes les valeurs du fichier sont masquées, même sans ${SECRET:...}
    assert redact_text(f"x {SECRET}").startswith("[1 line(s) hidden")


@pytest.mark.parametrize("text, fragment", [
    ("visibility: loud\n", "plain, masked, hidden"),
    ("provider: magic\n", "unknown provider 'magic'"),
    ("provider: vault\n", "not available in this version"),
    ("provider: sops\n", "needs sops.file"),
    ("visbility: masked\n", "unknown key(s): visbility"),
    ("- a\n", "expected a mapping"),
])
def test_settings_errors_are_explicit(proj, text, fragment):
    _settings(proj, text)
    with pytest.raises(SecretResolutionError) as e:
        project_secrets(proj)
    assert fragment in str(e.value)


# ── Intégration : workflow, CLI, undo, API ──────────────────────────────────
def test_action_output_logs_and_errors_are_masked(proj):
    set_secret(proj / ".hydra" / "secrets", "api.token", SECRET)
    _workflow(proj, "print('token=${SECRET:api.token}'); import sys; "
                    "print('err ${SECRET:api.token}', file=sys.stderr)", fail=True)
    res = _run_wf(proj)
    assert not res.success
    text = _all_text(res)
    assert SECRET not in text and MASK in text


def test_hidden_mode_in_a_workflow(proj):
    _settings(proj, "visibility: hidden\n")
    set_secret(proj / ".hydra" / "secrets", "api.token", SECRET)
    _workflow(proj, "print('before'); print('token=${SECRET:api.token}'); print('after')")
    res = _run_wf(proj)
    assert res.success
    out = res.steps[0].output
    assert out == ["before", "[1 line(s) hidden: they contain a secret]", "after"]
    assert SECRET not in _all_text(res)


def test_webhook_url_is_masked_in_logs_and_errors(proj):
    set_secret(proj / ".hydra" / "secrets", "api.token", SECRET)
    (proj / "workflows" / "s.yaml").write_text(textwrap.dedent("""\
        workflow:
          name: s
          steps:
            - name: hook
              type: action
              action: webhook
              params:
                url: "http://127.0.0.1:9/hook?token=${SECRET:api.token}"
        """), encoding="utf-8")
    res = _run_wf(proj)
    assert not res.success and SECRET not in _all_text(res)
    assert any(MASK in ln for ln in res.steps[0].logs)


def test_cli_output_is_masked_and_plain_shows_it(runner, proj):
    set_secret(proj / ".hydra" / "secrets", "api.token", SECRET)
    _workflow(proj, "print('token=${SECRET:api.token}')", fail=True)
    res = runner.invoke(cli, ["run", str(proj)])
    assert res.exit_code == 1 and SECRET not in res.output and MASK in res.output
    masking.clear()
    res = runner.invoke(cli, ["run", str(proj), "--secrets-visibility", "plain"])
    assert SECRET in res.output


def test_undo_report_is_masked(proj):
    set_secret(proj / ".hydra" / "secrets", "api.token", SECRET)
    undo_code = "import sys; print('undo ${SECRET:api.token}', file=sys.stderr); sys.exit(2)"
    (proj / "workflows" / "s.yaml").write_text(textwrap.dedent(f"""\
        workflow:
          name: s
          rollback: true
          steps:
            - name: first
              type: action
              action: python
              params:
                script: "print('ok')"
              undo:
                action: python
                params:
                  script: {json.dumps(undo_code)}
            - name: second
              type: action
              action: python
              params:
                script: "import sys; sys.exit(1)"
              depends_on: [first]
              undo: none
        """), encoding="utf-8")
    res = _run_wf(proj)
    assert not res.success and res.rollback and res.rollback["status"] == "failed"
    assert SECRET not in _all_text(res)
    assert MASK in json.dumps(res.rollback)
    journal = proj / ".hydra" / "undo" / "s.json"
    if journal.exists():
        assert SECRET not in journal.read_text(encoding="utf-8")


def test_api_run_store_is_masked():
    from hydra_etl.api import store
    from hydra_etl.api.models import RunResponse
    register(SECRET, "masked")
    run = RunResponse(run_id="r-mask", workflow_name="w", status="failed",
                      started_at="now", error=f"bad {SECRET}",
                      steps=[{"step_name": "a", "logs": [f"x {SECRET}"], "output": []}])
    store.save_run(run)
    assert SECRET not in store.get_run("r-mask").model_dump_json()


# ── SOPS + age ──────────────────────────────────────────────────────────────
needs_sops = pytest.mark.skipif(
    not (shutil.which("sops") and shutil.which("age-keygen")),
    reason="sops and age are not installed")


@pytest.fixture
def age_key(tmp_path, monkeypatch):
    key = tmp_path / "age.key"
    subprocess.run(["age-keygen", "-o", str(key)], check=True, capture_output=True)
    pub = next(ln.split(":", 1)[1].strip() for ln in key.read_text().splitlines()
               if ln.startswith("# public key:"))
    monkeypatch.setenv("SOPS_AGE_KEY_FILE", str(key))
    return pub


def _encrypt(plain: Path, out: Path, pub: str, kind: str) -> None:
    res = subprocess.run(["sops", "--encrypt", "--age", pub, "--input-type", kind,
                          "--output-type", kind, str(plain)], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    out.write_text(res.stdout, encoding="utf-8")
    plain.unlink()


@needs_sops
def test_sops_provider_yaml(proj, age_key, tmp_path):
    plain = tmp_path / "plain.yaml"
    plain.write_text(f"db:\n  password: {json.dumps(SECRET)}\napi:\n  token: tok-123456\n", encoding="utf-8")
    _encrypt(plain, proj / ".hydra" / "secrets.sops.yaml", age_key, "yaml")
    _settings(proj, "provider: sops\nsops:\n  file: .hydra/secrets.sops.yaml\n")
    enc = (proj / ".hydra" / "secrets.sops.yaml").read_text(encoding="utf-8")
    assert SECRET not in enc and "sops:" in enc
    r = SecretResolver(secrets={}, fallback=project_secrets(proj))
    assert r.resolve("${SECRET:db.password}") == SECRET
    assert r.resolve("${SECRET:api.token}") == "tok-123456"
    assert redact_text(f"x {SECRET} tok-123456") == f"x {MASK} {MASK}"


@needs_sops
def test_sops_environment_still_wins(proj, age_key, tmp_path, monkeypatch):
    plain = tmp_path / "p.yaml"
    plain.write_text("db:\n  password: from-sops-file\n", encoding="utf-8")
    _encrypt(plain, proj / ".hydra" / "s.enc.yaml", age_key, "yaml")
    _settings(proj, "provider: sops\nsops:\n  file: .hydra/s.enc.yaml\n")
    monkeypatch.setenv("DB_PASSWORD", "from-env")
    assert SecretResolver(secrets={}, fallback=project_secrets(proj)).resolve(
        "${SECRET:db.password}") == "from-env"


@needs_sops
def test_encrypted_local_file_is_detected(proj, age_key, tmp_path, runner):
    plain = tmp_path / "secrets.env"
    plain.write_text(f"api.token={SECRET}\n", encoding="utf-8")
    target = proj / ".hydra" / "secrets"
    _encrypt(plain, target, age_key, "dotenv")
    assert project_secrets(proj) == {"api.token": SECRET}
    with pytest.raises(SecretResolutionError, match="encrypted with sops"):
        set_secret(target, "x", "y")
    with pytest.raises(SecretResolutionError, match="encrypted with sops"):
        delete_secret(target, "api.token")
    _workflow(proj, "print('token=${SECRET:api.token}')", fail=True)
    res = runner.invoke(cli, ["run", str(proj)])
    assert res.exit_code == 1 and SECRET not in res.output and MASK in res.output


@needs_sops
def test_sops_wrong_key_is_explained(proj, age_key, tmp_path, monkeypatch):
    plain = tmp_path / "p.yaml"
    plain.write_text("k: value-12345\n", encoding="utf-8")
    _encrypt(plain, proj / ".hydra" / "s.enc.yaml", age_key, "yaml")
    other = tmp_path / "other.key"
    subprocess.run(["age-keygen", "-o", str(other)], check=True, capture_output=True)
    monkeypatch.setenv("SOPS_AGE_KEY_FILE", str(other))
    _settings(proj, "provider: sops\nsops:\n  file: .hydra/s.enc.yaml\n")
    with pytest.raises(SecretResolutionError) as e:
        SecretResolver(secrets={}, fallback=project_secrets(proj)).resolve("${SECRET:k}")
    assert "cannot decrypt" in str(e.value) and "value-12345" not in str(e.value)


def test_sops_missing_binary_is_explained(proj, monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    monkeypatch.delenv("HYDRA_SOPS_BIN", raising=False)
    (proj / ".hydra" / "s.enc.yaml").write_text("k: ENC[x]\nsops:\n  version: 3\n", encoding="utf-8")
    _settings(proj, "provider: sops\nsops:\n  file: .hydra/s.enc.yaml\n")
    with pytest.raises(SecretResolutionError, match="sops is not installed"):
        SecretResolver(secrets={}, fallback=project_secrets(proj)).resolve("${SECRET:k}")
