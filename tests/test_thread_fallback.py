"""Fallback dans thread.yaml — étape 1 : déclaration, validation, contrôle au
--dry-run (pas encore de bascule à l'exécution)."""
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from hydra_etl.cli.hdrctl import cli
from hydra_etl.workflow.conditions import ConditionError, condition_sources, parse_condition
from hydra_etl.workflow.project import ProjectError, add_workflow, list_workflows, prepare_project, remove_workflow
from hydra_etl.workflow.thread import parse_thread, remove_from_thread, render_thread

VS_EXAMPLE = Path(__file__).resolve().parents[1] / "vscode-extension" / "examples" / "valid_workflow" / "thread.yaml"


# ── Langage des conditions ──────────────────────────────────────────────────

@pytest.mark.parametrize("cond", [
    "not source_available('crm_db')",
    "file_size('data/in.csv') < 1MB or file_age('data/in.csv') > 24h",
    "previous.status == 'failed' and previous.rows < 100",
    "db.load('crm') >= 50",
    "url_ok('https://api.example.com/health') and secret_defined('api.token')",
    "destination_available('dw') and file_exists('x.csv')",
])
def test_conditions_accepted(cond):
    parse_condition(cond)


@pytest.mark.parametrize("cond, words", [
    ("__import__('os').system('x')", "only names like"),
    ("open('f')", "unknown function"),
    ("source_available(crm)", "quoted"),
    ("source_available('a', 'b')", "1 argument"),
    ("estimate.duration > 30m", "reserved for 'adapt'"),
    ("resources.free_memory < 2GB", "reserved for 'adapt'"),
    ("previous.status in ['a']", "comparisons"),
    ("file_size('a') + 1 > 3", "not allowed"),
    ("lambda: 1", "not allowed"),
    ("source_available", "is a function"),
    ("", "empty"),
    ("not (", "syntax error"),
])
def test_conditions_refused(cond, words):
    with pytest.raises(ConditionError) as e:
        parse_condition(cond)
    assert words in str(e.value)


def test_units_are_not_expanded_inside_strings():
    tree, _ = parse_condition("file_age('logs/24h.csv') > 24h")
    assert ("file_age", "logs/24h.csv") in condition_sources("file_age('logs/24h.csv') > 24h")
    assert "86400" in __import__("ast").unparse(tree)


# ── Modèle thread.yaml ──────────────────────────────────────────────────────

def T(text):
    return parse_thread(yaml.safe_load(text))


def test_fallback_parsed_and_rendered_without_loss():
    th = T("""
thread:
  - workflows:
      - name: a
        fallback: {use: a_backup, when: "not source_available('db') or file_age('x') > 24h", on_failure: true}
      - name: c
        fallback: {use: [b1, b2], on_failure: true, on_probe_error: replace}
""")
    assert th.thread[0].workflows[0].fallback.use == ["a_backup"]          # un nom → liste
    assert th.fallback_names() == ["a_backup", "b1", "b2"]
    assert T(render_thread(th)) == th


@pytest.mark.parametrize("text, words", [
    ("{thread: [{workflows: [{name: a, fallback: {use: [a], on_failure: true}}]}]}", "cannot be the workflow itself"),
    ("{thread: [{workflows: [{name: a, fallback: {use: [b], on_failure: true}}, {name: b}]}]}", "already in the thread"),
    ("{thread: [{workflows: [{name: a, fallback: {use: [b]}}]}]}", "needs 'when'"),
    ("{thread: [{workflows: [{name: a, fallback: {use: [b, b], on_failure: true}}]}]}", "more than once"),
    ("{thread: [{workflows: [{name: a, fallback: {use: [], on_failure: true}}]}]}", "use"),
    ("{thread: [{workflows: [{name: a, fallback: {use: [b], when: 'estimate.duration > 1h'}}]}]}", "adapt"),
    ("{thread: [{workflows: [{name: a, fallback: {use: [b], on_failure: true, retry: 2}}]}]}", "retry"),
])
def test_invalid_fallbacks(text, words):
    with pytest.raises(ValueError) as e:
        T(text)
    assert words in str(e.value)


def test_removing_a_backup_updates_fallbacks():
    th = T("{thread: [{workflows: [{name: a, fallback: {use: [b, c], on_failure: true}}, "
           "{name: d, fallback: {use: [b], on_failure: true}}]}]}")
    th2, found = remove_from_thread(th, "b")
    assert not found                                    # b n'est pas dans le thread
    assert th2.thread[0].workflows[0].fallback.use == ["c"]
    assert th2.thread[0].workflows[1].fallback is None  # plus de remplaçant → plus de fallback


def test_vscode_example_is_valid_for_hydra():
    T(VS_EXAMPLE.read_text(encoding="utf-8"))


# ── Projet : add / list / remove / dry-run ──────────────────────────────────

@pytest.fixture
def proj(tmp_path, monkeypatch):
    root = tmp_path / "p"
    assert CliRunner().invoke(cli, ["init", str(root), "-q"]).exit_code == 0
    monkeypatch.chdir(root)
    return root


def run(*args):
    return CliRunner().invoke(cli, [*args, "--lang", "en"])


def test_add_fallback_for_then_list_and_remove(proj):
    r = run("workflow", "add", "workflow1_backup", "--fallback-for", "workflow1")
    assert r.exit_code == 0, r.output
    assert "Fallback of workflow1" in r.output
    th = (proj / "workflows" / "thread.yaml").read_text(encoding="utf-8")
    assert "use: [workflow1_backup]" in th and "on_failure: true" in th
    assert "- name: workflow1_backup" not in th                  # pas dans le thread
    items, _ = list_workflows(proj)
    backup = next(i for i in items if i.name == "workflow1_backup")
    assert backup.stage is None and backup.fallback_of == ["workflow1"]
    assert "fallback of workflow1" in run("workflow", "list").output
    assert run("workflow", "remove", "workflow1_backup", "-y").exit_code == 0
    assert "fallback" not in (proj / "workflows" / "thread.yaml").read_text(encoding="utf-8").split('version: "1.0"')[1]


def test_fallback_for_unknown_workflow(proj):
    with pytest.raises(ProjectError) as e:
        add_workflow(proj, "x_backup", fallback_for="nope")
    assert "not in workflows/thread.yaml" in str(e.value)


def test_add_of_a_declared_backup_does_not_enter_the_thread(proj):
    tf = proj / "workflows" / "thread.yaml"
    tf.write_text(tf.read_text(encoding="utf-8").replace(
        "        active: true", "        active: true\n        fallback: {use: [bk], on_failure: true}"), encoding="utf-8")
    name, path, th = add_workflow(proj, "bk")
    assert path.is_file() and "bk" not in th.workflow_names()


def _set_fallback(proj, fallback: str):
    tf = proj / "workflows" / "thread.yaml"
    txt = tf.read_text(encoding="utf-8").replace("        active: true", "        active: true\n" + fallback)
    tf.write_text(txt, encoding="utf-8")


def test_dry_run_shows_fallback_and_warns_on_other_destination(proj):
    run("workflow", "add", "workflow1_backup", "--fallback-for", "workflow1")
    r = run("run", ".", "--dry-run")
    assert r.exit_code == 0, r.output
    assert "fallback: workflow1_backup (on failure)" in r.output
    assert "writes to nothing instead of ['csv:data/output.csv']" in r.output     # remplaçant vide


def test_backup_with_same_destination_has_no_warning(proj):
    run("workflow", "add", "workflow1_backup", "--fallback-for", "workflow1")
    assert run("job", "attach", "job1", "workflow1_backup").exit_code == 0
    plan = prepare_project(proj)
    assert plan.warnings == []
    assert "workflow1_backup" in plan.workflows              # chargé et vérifié


def test_dry_run_refuses_missing_backup_and_unknown_names(proj):
    _set_fallback(proj, "        fallback:\n          use: [ghost]\n"
                        "          when: \"not source_available('nope') or destination_available('dest_csv')\"")
    with pytest.raises(ProjectError) as e:
        prepare_project(proj)
    msg = " | ".join(e.value.errors)
    assert "'ghost' has no file workflows/ghost.yaml" in msg
    assert "source_available('nope')" in msg
    assert "dest_csv" not in msg                              # déclarée dans job1


def test_inactive_workflow_fallback_is_not_checked(proj):
    _set_fallback(proj, "        fallback: {use: [ghost], on_failure: true}")
    tf = proj / "workflows" / "thread.yaml"
    tf.write_text(tf.read_text(encoding="utf-8").replace("active: true", "active: false"), encoding="utf-8")
    prepare_project(proj)                                     # pas d'erreur


def test_studio_keeps_fallback_on_save(tmp_path, monkeypatch, proj):
    from fastapi.testclient import TestClient
    from hydra_etl.api import store
    monkeypatch.setattr(store, "WORKSPACE", tmp_path / "ws")
    monkeypatch.setattr(store, "_INDEX_FILE", tmp_path / "ws" / "index.json")
    (tmp_path / "ws").mkdir()
    import hydra_etl.api.main as main
    client = TestClient(main.app)
    run("workflow", "add", "workflow1_backup", "--fallback-for", "workflow1")
    p = store.open_project(str(proj))
    got = client.get(f"/api/projects/{p.id}/thread").json()
    stages = got["thread"]["thread"]
    assert stages[0]["workflows"][0]["fallback"]["use"] == ["workflow1_backup"]
    r = client.put(f"/api/projects/{p.id}/thread", json={"thread": stages, "loops": []})
    assert r.status_code == 200, r.text
    assert "use: [workflow1_backup]" in (proj / "workflows" / "thread.yaml").read_text(encoding="utf-8")
    chk = client.post(f"/api/projects/{p.id}/check").json()
    assert chk["ok"] and any("writes to nothing" in w for w in chk["warnings"])
