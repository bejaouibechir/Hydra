"""Fallback — étape 2 : sondes et bascule avant le lancement."""
from __future__ import annotations

import http.server
import json
import textwrap
import threading
import time
from pathlib import Path

import pytest
from click.testing import CliRunner

from hydra_etl.cli.hdrctl import cli
from hydra_etl.workflow import probes
from hydra_etl.workflow.probes import Previous, ProbeContext, ProbeError, evaluate
from hydra_etl.workflow.project import (
    FAILED, INACTIVE, SUCCESS, ProjectError, ProjectRunner, prepare_project,
)


# ── Projet de test : workflows à une action python qui écrivent dans log.txt ─

@pytest.fixture
def root(tmp_path):
    r = tmp_path / "proj"
    assert CliRunner().invoke(cli, ["init", str(r), "-q"]).exit_code == 0
    return r


def wf(root: Path, name: str, extra: str = "") -> None:
    log = (root / "log.txt").as_posix()
    script = f"open(r'{log}', 'a').write('{name}\\n'){extra}"
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


def thread(root: Path, body: str) -> None:
    (root / "workflows" / "thread.yaml").write_text(
        'version: "1.0"\nthread:\n' + textwrap.dedent(body), encoding="utf-8")


def log(root: Path) -> list:
    f = root / "log.txt"
    return f.read_text(encoding="utf-8").split() if f.exists() else []


def run(root: Path, **kw):
    events = []
    result = ProjectRunner(prepare_project(root), **kw).run(lambda k, d: events.append((k, d)))
    return result, events


# ── Sondes ──────────────────────────────────────────────────────────────────

def ctx(root, **kw):
    return ProbeContext(root=root, **kw)


def test_file_probes(root):
    (root / "flag.txt").write_text("12345", encoding="utf-8")
    assert evaluate("file_exists('flag.txt')", ctx(root)).value
    assert not evaluate("file_exists('nope.txt')", ctx(root)).value
    ev = evaluate("file_size('flag.txt') == 5 and file_age('flag.txt') < 1h", ctx(root))
    assert ev.value and "file_size('flag.txt') = 5" in ev.reason
    with pytest.raises(ProbeError, match="file not found"):
        evaluate("file_size('nope.txt') > 0", ctx(root))


def test_short_circuit_avoids_probe_errors(root):
    # file_size n'est pas évalué quand le fichier n'existe pas
    assert not evaluate("file_exists('nope') and file_size('nope') > 0", ctx(root)).value
    assert evaluate("not file_exists('nope') or file_size('nope') < 10", ctx(root)).value


def test_secret_defined(root, monkeypatch):
    monkeypatch.delenv("API_TOKEN", raising=False)
    assert not evaluate("secret_defined('api.token')", ctx(root)).value
    (root / ".hydra" / "secrets").write_text("api.token=xyz\n", encoding="utf-8")
    assert evaluate("secret_defined('api.token')", ctx(root)).value


def test_url_ok(root):
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(200 if self.path == "/ok" else 503)
            self.end_headers()

        def log_message(self, *a):
            pass
    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        assert evaluate(f"url_ok('{base}/ok')", ctx(root)).value
        ev = evaluate(f"url_ok('{base}/down')", ctx(root))
        assert not ev.value and "HTTP 503" in ev.reason
        assert not evaluate("url_ok('http://127.0.0.1:9/')", ctx(root, timeout=3)).value
    finally:
        srv.shutdown()


def test_source_and_destination_available_csv(root):
    job = root / "jobs" / "job1"
    assert evaluate("source_available('src_csv')", ctx(root, workflow_jobs=[job])).value
    assert evaluate("destination_available('dest_csv')", ctx(root)).value
    (job / "data" / "input.csv").unlink()
    ev = evaluate("source_available('src_csv')", ctx(root))
    assert not ev.value and "file not found" in ev.reason
    with pytest.raises(ProbeError, match="not declared"):
        evaluate("source_available('ghost')", ctx(root))
    with pytest.raises(ProbeError, match="not a supported database"):
        evaluate("db.load('src_csv') > 10", ctx(root))


def test_probe_timeout(root, monkeypatch):
    monkeypatch.setitem(probes.PROBES, "file_exists", lambda a, c: time.sleep(5))
    t0 = time.monotonic()
    with pytest.raises(ProbeError, match="timed out"):
        evaluate("file_exists('x')", ctx(root, timeout=0.3))
    assert time.monotonic() - t0 < 2


def test_previous_values(root):
    c = ctx(root, previous=Previous(status="success", rows=42))
    assert evaluate("previous.status == 'success' and previous.rows > 40", c).value


# ── Bascule dans le run ─────────────────────────────────────────────────────

FB = """\
  - mode: sequential
    workflows:
      - name: a
        fallback:
          use: [a_backup]
          when: "file_exists('flag')"
      - name: b
"""


@pytest.fixture
def proj(root):
    for n in ("a", "a_backup", "b"):
        wf(root, n)
    thread(root, FB)
    return root


def test_condition_false_keeps_the_workflow(proj):
    result, events = run(proj)
    assert result.success and log(proj) == ["a", "b"]
    kept = [d for k, d in events if k == "fallback_kept"]
    assert kept and "file_exists('flag') = false" in kept[0]["reason"]


def test_condition_true_switches_in_place(proj):
    (proj / "flag").write_text("x")
    result, events = run(proj)
    assert result.success and log(proj) == ["a_backup", "b"]
    fb = [d for k, d in events if k == "fallback"][0]
    assert fb["name"] == "a" and fb["use"] == "a_backup" and fb["trigger"] == "when"
    r = result.runs[0]
    assert r.name == "a_backup" and r.replaces == "a" and "file_exists('flag') = true" in r.fallback_reason
    start = [d for k, d in events if k == "start"][0]
    assert start["replaces"] == "a"


def test_forced_fallback(proj):
    result, events = run(proj, force_fallback=["a"])
    assert log(proj) == ["a_backup", "b"]
    assert [d for k, d in events if k == "fallback"][0]["trigger"] == "forced"
    with pytest.raises(ProjectError, match="has no fallback"):
        ProjectRunner(prepare_project(proj), force_fallback=["b"])


@pytest.mark.parametrize("policy, expected, kind", [
    ("keep", ["a", "b"], "probe_error"),
    ("replace", ["a_backup", "b"], "fallback"),
])
def test_probe_error_policy(proj, policy, expected, kind):
    thread(proj, FB.replace("when: \"file_exists('flag')\"",
                            f"when: \"file_size('missing.csv') < 10\"\n          on_probe_error: {policy}"))
    result, events = run(proj)
    assert result.success and log(proj) == expected
    assert any(k == kind for k, _ in events)


def test_inactive_workflow_is_not_checked(proj, monkeypatch):
    thread(proj, FB.replace("      - name: a\n", "      - name: a\n        active: false\n"))
    called = []
    monkeypatch.setitem(probes.PROBES, "file_exists", lambda a, c: called.append(a) or (True, ""))
    result, _ = run(proj)
    assert log(proj) == ["b"] and called == [] and result.runs[0].status == INACTIVE


def test_parallel_stage(proj):
    (proj / "flag").write_text("x")
    thread(proj, FB.replace("mode: sequential", "mode: parallel"))
    result, _ = run(proj)
    assert sorted(log(proj)) == ["a_backup", "b"]


def test_loop_reevaluates_each_pass(root):
    for n in ("a", "a_backup"):
        wf(root, n)
    flag = (root / "flag").as_posix()
    wf(root, "b", extra=f"; open(r'{flag}', 'w').write('x')")     # b crée le drapeau
    thread(root, FB + "loops:\n  - {from: b, to: a, times: 2}\n")
    result, _ = run(root, sleep=lambda s: None)
    assert log(root) == ["a", "b", "a_backup", "b"]               # 2e passage : bascule


def test_previous_status_and_rows(root):
    for n in ("a", "b", "b_backup"):
        wf(root, n)
    thread(root, """\
  - mode: sequential
    workflows:
      - name: a
      - name: b
        fallback:
          use: [b_backup]
          when: "previous.status == 'success' and previous.rows == 0"
""")
    result, _ = run(root)
    assert log(root) == ["a", "b_backup"]                          # action : 0 ligne


def test_cli_shows_the_switch(proj):
    (proj / "flag").write_text("x")
    r = CliRunner().invoke(cli, ["run", str(proj), "--lang", "en"])
    assert r.exit_code == 0, r.output
    assert "Fallback: a → a_backup — file_exists('flag') = true" in r.output
    assert "(fallback, in place of a)" in r.output
    r = CliRunner().invoke(cli, ["run", str(proj / "jobs" / "job1"), "--use-fallback", "a", "--lang", "en"])
    assert r.exit_code == 1 and "applies to a project" in r.output
    r = CliRunner().invoke(cli, ["run", str(proj), "--dry-run", "--use-fallback", "b", "--lang", "en"])
    assert r.exit_code == 1 and "has no fallback" in r.output


def test_studio_run_shows_the_switch(proj, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from hydra_etl.api import store
    monkeypatch.setattr(store, "WORKSPACE", tmp_path / "ws")
    monkeypatch.setattr(store, "_INDEX_FILE", tmp_path / "ws" / "index.json")
    (tmp_path / "ws").mkdir()
    import hydra_etl.api.main as main
    client = TestClient(main.app)
    (proj / "flag").write_text("x")
    store.open_project(str(proj))
    rid = client.post("/api/runs", json={"workflow_path": str(proj)}).json()["run_id"]
    for _ in range(100):
        run_ = client.get(f"/api/runs/{rid}").json()
        if run_["status"] in ("success", "failed"):
            break
        time.sleep(0.1)
    assert run_["status"] == "success", run_
    s0 = run_["steps"][0]
    assert s0["step_name"] == "a_backup — fallback of a"
    assert s0["logs"][0].startswith("FALLBACK a -> a_backup (when): file_exists('flag') = true")
