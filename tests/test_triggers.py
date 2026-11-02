"""Déclencheurs de projet — triggers.yaml, contrôles, historique, fire (0.19, lot 2.1)."""
import json
import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from hydra_etl.triggers.core import check_triggers, fire, read_history
from hydra_etl.triggers.models import TriggerFile, TriggerFileError, load_triggers

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _importable(monkeypatch):
    # fire lance toujours le projet dans un processus séparé (hdrctl)
    monkeypatch.setenv("PYTHONPATH", str(REPO) + os.pathsep + os.environ.get("PYTHONPATH", ""))


def _project(base: Path, name: str, script: str = 'print("hello")', triggers: str = "") -> Path:
    root = base / name
    (root / ".hydra").mkdir(parents=True)
    (root / ".hydra" / "project.json").write_text(json.dumps({"id": name, "name": name}))
    (root / "workflows").mkdir()
    (root / "workflows" / "main.yaml").write_text(
        "workflow:\n  name: main\n  steps:\n    - name: s\n      type: action\n      action: python\n"
        f"      params:\n        script: '{script}'\n")
    (root / "workflows" / "thread.yaml").write_text(
        "thread:\n  - mode: sequential\n    workflows:\n      - name: main\n")
    if triggers:
        (root / "triggers.yaml").write_text(triggers)
    return root


# ── Modèle ────────────────────────────────────────────────────────────────

def test_every_type_is_accepted():
    tf = TriggerFile(triggers=[
        dict(name="a", type="cron", cron="0 2 * * *", env="prod", workflows=["main"], retry={"max": 2}),
        dict(name="b", type="interval", every="15m"),
        dict(name="c", type="file", path="inbox/*.csv", events=["added", "modified"], debounce="5s"),
        dict(name="d", type="marker", path="inbox/READY", consume=False),
        dict(name="e", type="source_change", source={"job": "jobs/x", "id": "orders", "check": "max",
                                                     "column": "updated_at"}, every="1m"),
        dict(name="f", type="webhook", token="${SECRET:trigger.f.token}"),
        dict(name="g", type="after_project", project="../crm", on="failure"),
    ])
    assert [t.type for t in tf.triggers] == ["cron", "interval", "file", "marker", "source_change",
                                             "webhook", "after_project"]
    assert tf.get("a").overlap == "skip" and tf.get("c").events_effective == ["added", "modified"]


@pytest.mark.parametrize("t, msg", [
    (dict(name="a", type="cron"), "requires 'cron'"),
    (dict(name="a", type="cron", cron="61 * * * *"), "cron '61 * * * *'"),
    (dict(name="a", type="cron", cron="0 2 * *"), "5 fields"),
    (dict(name="a", type="interval", every="0s"), "every must be more than 0"),
    (dict(name="a", type="interval", every="soon"), "invalid delay"),
    (dict(name="a", type="interval", every="5m", path="x"), "path does not apply to type interval"),
    (dict(name="a", type="file", path="../x"), "must stay inside the project"),
    (dict(name="a", type="file", path="C:/x"), "must stay inside the project"),
    (dict(name="a", type="webhook", token="plain"), "secret reference"),
    (dict(name="a", type="cron", cron="0 2 * * *", params={"pw": "${SECRET:db}"}), "holds a secret"),
    (dict(name="a", type="cron", cron="0 2 * * *", workflows=[]), "workflows is empty"),
    (dict(name="a", type="cron", cron="0 2 * * *", retry={"max": 0}), "retry.max"),
    (dict(name="a", type="source_change", source={"job": "j", "id": "s", "check": "max"}), "requires source.column"),
    (dict(name="bad name", type="interval", every="1m"), "trigger name"),
    (dict(name="a", type="hourly"), "type"),
    (dict(name="a", type="interval", every="1m", unknown=1), "unknown"),
])
def test_invalid_triggers(t, msg):
    with pytest.raises(Exception, match=msg.replace("*", r"\*").replace("(", r"\(")):
        TriggerFile(triggers=[t])


def test_duplicate_names_refused():
    with pytest.raises(Exception, match="used twice"):
        TriggerFile(triggers=[dict(name="a", type="interval", every="1m")] * 2)


def test_yaml_on_key_is_read(tmp_path):
    root = _project(tmp_path, "p", triggers="triggers:\n  - name: x\n    type: after_project\n"
                                             "    project: ../q\n    on: failure\n")
    assert load_triggers(root).get("x").on == "failure"


def test_missing_file_means_no_trigger(tmp_path):
    assert load_triggers(_project(tmp_path, "p")).triggers == []


def test_load_reports_messages(tmp_path):
    root = _project(tmp_path, "p", triggers="triggers:\n  - name: x\n    type: cron\n")
    with pytest.raises(TriggerFileError) as e:
        load_triggers(root)
    assert any("requires 'cron'" in m for m in e.value.errors)


# ── Contrôles du projet ───────────────────────────────────────────────────

def test_check_workflows_source_secret(tmp_path):
    root = _project(tmp_path, "p", triggers=(
        "triggers:\n"
        "  - {name: a, type: interval, every: 1m, workflows: [nope]}\n"
        "  - {name: b, type: source_change, source: {job: jobs/x, id: orders}}\n"
        "  - {name: c, type: webhook, token: '${SECRET:trigger.c.token}'}\n"
        "  - {name: d, type: after_project, project: ../ghost}\n"
        "  - {name: e, type: after_project, project: .}\n"))
    res = check_triggers(root)
    text = "\n".join(res.errors)
    assert "workflow(s) not found: nope" in text
    assert "not a job folder" in text
    assert "ghost" in text
    assert "cannot be started by its own end" in text
    assert any("trigger.c.token" in w for w in res.warnings)


def test_check_after_project_loop(tmp_path):
    a = _project(tmp_path, "a", triggers="triggers:\n  - {name: x, type: after_project, project: ../b}\n")
    _project(tmp_path, "b", triggers="triggers:\n  - {name: y, type: after_project, project: ../a}\n")
    assert any("after_project loop" in e for e in check_triggers(a).errors)


def test_check_reports_project_step_cycle(tmp_path):
    a = _project(tmp_path, "a", triggers="triggers:\n  - {name: x, type: interval, every: 1m}\n")
    (a / "workflows" / "main.yaml").write_text(
        "workflow:\n  name: main\n  steps:\n    - {name: me, type: project, project: .}\n")
    assert any("calls itself" in e for e in check_triggers(a).errors)


# ── Lancement ─────────────────────────────────────────────────────────────

def test_fire_success_and_history(tmp_path):
    root = _project(tmp_path, "p", script='print("fired")',
                    triggers="triggers:\n  - {name: t, type: interval, every: 1m}\n")
    res = fire(root, load_triggers(root).get("t"), origin="manual")
    assert res.status == "success", res.error
    assert any("fired" in l for l in res.lines)
    h = read_history(root)
    assert h[-1]["trigger"] == "t" and h[-1]["status"] == "success" and h[-1]["origin"] == "manual"


def test_fire_retries_after_failure(tmp_path):
    root = _project(tmp_path, "p", script="raise SystemExit(3)",
                    triggers="triggers:\n  - {name: t, type: interval, every: 1m, "
                             "retry: {max: 1, delay: 0s}}\n")
    res = fire(root, load_triggers(root).get("t"))
    assert res.status == "failed" and res.attempts == 2
    assert [e["attempt"] for e in read_history(root, "t")] == [1, 2]


def test_fire_overlap_skip(tmp_path):
    from hydra_etl.workflow.subprojects import _acquire, _release
    root = _project(tmp_path, "p", triggers="triggers:\n  - {name: t, type: interval, every: 1m}\n")
    assert _acquire(root.resolve(), "skip", None)
    try:
        res = fire(root, load_triggers(root).get("t"))
    finally:
        _release(root.resolve())
    assert res.status == "skipped"


def test_cli_list_validate_fire(tmp_path):
    from hydra_etl.cli.hdrctl import cli
    root = _project(tmp_path, "p", script='print("cli")',
                    triggers="triggers:\n  - {name: t, type: cron, cron: '0 2 * * *'}\n")
    r = CliRunner()
    out = r.invoke(cli, ["trigger", "list", "--project", str(root)])
    assert out.exit_code == 0 and "cron 0 2 * * *" in out.output
    assert r.invoke(cli, ["trigger", "validate", "--project", str(root)]).exit_code == 0
    out = r.invoke(cli, ["trigger", "fire", "t", "--project", str(root)])
    assert out.exit_code == 0, out.output
    assert "cli" in out.output
    assert r.invoke(cli, ["trigger", "fire", "nope", "--project", str(root)]).exit_code == 1
    out = r.invoke(cli, ["trigger", "history", "--project", str(root)])
    assert "manual" in out.output
