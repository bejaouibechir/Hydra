"""`hdrctl workflow add | remove | list` et la résolution par nom de
`workflow run | validate`. Un projet est un ensemble de workflows, ordonnés par
workflows/thread.yaml."""
from __future__ import annotations

import json
import re
import textwrap
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from hydra_etl.cli.hdrctl import cli
from hydra_etl.workflow.project import add_workflow, list_workflows, remove_workflow
from hydra_etl.workflow.thread import load_thread


@pytest.fixture
def runner():
    return CliRunner(env={"HYDRA_LANG": "en"})


@pytest.fixture
def proj(tmp_path, runner):
    root = tmp_path / "proj"
    assert runner.invoke(cli, ["init", str(root), "-q"]).exit_code == 0
    return root


def _thread(root: Path) -> list:
    th = load_thread(root / "workflows" / "thread.yaml")
    return [(s.mode, [(w.name, w.active) for w in s.workflows]) for s in th.thread]


def _write_thread(root: Path, body: str) -> None:
    (root / "workflows" / "thread.yaml").write_text(
        'version: "1.0"\nthread:\n' + textwrap.dedent(body), encoding="utf-8")


# ── add ───────────────────────────────────────────────────────────────────────

def test_add_creates_empty_workflow_at_end_of_thread(runner, proj, monkeypatch):
    monkeypatch.chdir(proj)
    res = runner.invoke(cli, ["workflow", "add", "daily_sales"])
    assert res.exit_code == 0, res.output
    doc = yaml.safe_load((proj / "workflows" / "daily_sales.yaml").read_text(encoding="utf-8"))
    assert doc["workflow"]["name"] == "daily_sales"
    assert doc["workflow"]["steps"] == []
    assert _thread(proj) == [("sequential", [("workflow1", True), ("daily_sales", True)])]
    assert "hdrctl run . --dry-run" in res.output


def test_add_without_name_uses_guid(runner, proj, monkeypatch):
    monkeypatch.chdir(proj / "jobs")            # sous-dossier du projet
    res = runner.invoke(cli, ["workflow", "add"])
    assert res.exit_code == 0, res.output
    names = [p.stem for p in (proj / "workflows").glob("workflow-*.yaml")]
    assert len(names) == 1 and re.fullmatch(r"workflow-[0-9a-f]{8}", names[0])
    assert names[0] in [n for _, ws in _thread(proj) for n, _ in ws]


def test_add_after_parallel_stage_opens_new_stage(proj):
    _write_thread(proj, """\
        - mode: parallel
          workflows:
            - name: workflow1
        """)
    add_workflow(proj, "next_one")
    assert _thread(proj) == [("parallel", [("workflow1", True)]),
                             ("sequential", [("next_one", True)])]


def test_add_without_thread_file_creates_it(proj):
    (proj / "workflows" / "thread.yaml").unlink()
    (proj / "workflows" / "alpha.yaml").write_text("workflow:\n  name: alpha\n  steps: []\n", encoding="utf-8")
    add_workflow(proj, "zeta")
    assert _thread(proj) == [("sequential", [("alpha", True), ("workflow1", True), ("zeta", True)])]


def test_add_with_project_option_from_outside(runner, proj, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    res = runner.invoke(cli, ["workflow", "add", "w2", "--project", str(proj)])
    assert res.exit_code == 0, res.output
    assert (proj / "workflows" / "w2.yaml").is_file()


def test_add_outside_project_fails(runner, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    res = runner.invoke(cli, ["workflow", "add", "w"])
    assert res.exit_code == 1
    assert "not inside a Hydra project" in res.output and "--project" in res.output
    assert not (tmp_path / "workflows").exists()


@pytest.mark.parametrize("name", ["workflow1", "../evil", "a b", "-x"])
def test_add_rejects_existing_or_invalid_names(runner, proj, name):
    before = (proj / "workflows" / "thread.yaml").read_text(encoding="utf-8")
    res = runner.invoke(cli, ["workflow", "add", name, "--project", str(proj)])
    assert res.exit_code != 0
    assert (proj / "workflows" / "thread.yaml").read_text(encoding="utf-8") == before


def test_added_empty_workflow_runs_with_project(runner, proj):
    add_workflow(proj, "empty")
    res = runner.invoke(cli, ["run", str(proj)])
    assert res.exit_code == 0, res.output
    assert "2/2" in res.output


# ── remove ────────────────────────────────────────────────────────────────────

def test_remove_asks_confirmation(runner, proj):
    add_workflow(proj, "w2")
    res = runner.invoke(cli, ["workflow", "remove", "w2", "--project", str(proj)], input="n\n")
    assert res.exit_code == 0
    assert (proj / "workflows" / "w2.yaml").is_file()
    assert "Cancelled" in res.output


def test_remove_deletes_file_and_thread_entry_keeps_jobs(runner, proj):
    _write_thread(proj, """\
        - workflows:
            - name: workflow1
        - mode: parallel
          workflows:
            - name: w2
        """)
    (proj / "workflows" / "w2.yaml").write_text("workflow:\n  name: w2\n  steps: []\n", encoding="utf-8")
    res = runner.invoke(cli, ["workflow", "remove", "workflow1", "-y", "--project", str(proj)])
    assert res.exit_code == 0, res.output
    assert not (proj / "workflows" / "workflow1.yaml").exists()
    assert _thread(proj) == [("parallel", [("w2", True)])]      # étape vide supprimée
    assert (proj / "jobs" / "job1" / "pipeline.yaml").is_file()   # jobs conservés


def test_remove_also_cleans_studio_metadata(proj):
    meta = proj / ".hydra" / "workflows" / "ab12cd34.json"
    meta.parent.mkdir(parents=True, exist_ok=True)
    meta.write_text(json.dumps({"id": "ab12cd34", "name": "workflow1",
                                "path": str(proj / "workflows" / "workflow1.yaml")}), encoding="utf-8")
    manifest = proj / ".hydra" / "project.json"
    m = json.loads(manifest.read_text(encoding="utf-8"))
    m["workflows"] = [{"id": "ab12cd34", "name": "workflow1", "file": "workflows/workflow1.yaml"},
                      {"id": "zz", "name": "keep", "file": "workflows/keep.yaml"}]
    manifest.write_text(json.dumps(m), encoding="utf-8")
    remove_workflow(proj, "workflow1")
    assert not meta.exists()
    assert [w["id"] for w in json.loads(manifest.read_text(encoding="utf-8"))["workflows"]] == ["zz"]


def test_remove_thread_entry_without_file(proj):
    _write_thread(proj, "- workflows:\n    - name: workflow1\n    - name: ghost\n")
    removed, in_thread = remove_workflow(proj, "ghost")
    assert removed is None and in_thread is True
    assert _thread(proj) == [("sequential", [("workflow1", True)])]


def test_remove_unknown_fails(runner, proj):
    res = runner.invoke(cli, ["workflow", "remove", "nope", "-y", "--project", str(proj)])
    assert res.exit_code == 1
    assert "not found" in res.output


# ── list ──────────────────────────────────────────────────────────────────────

def test_list_shows_thread_order_and_statuses(runner, proj):
    for n in ("b_inactive", "c_orphan"):
        (proj / "workflows" / f"{n}.yaml").write_text(f"workflow:\n  name: {n}\n  steps: []\n", encoding="utf-8")
    (proj / "workflows" / "d_bad.yaml").write_text("workflow:\n  name: d\n  steps: nope\n", encoding="utf-8")
    _write_thread(proj, """\
        - workflows:
            - name: workflow1
            - name: b_inactive
              active: false
        - mode: parallel
          workflows:
            - name: ghost
            - name: d_bad
        """)
    items, implicit = list_workflows(proj)
    assert implicit is False
    got = [(i.name, i.stage, i.active, i.path is not None, i.error is not None) for i in items]
    assert got == [("workflow1", 1, True, True, False), ("b_inactive", 1, False, True, False),
                   ("ghost", 2, True, False, False), ("d_bad", 2, True, True, True),
                   ("c_orphan", None, None, True, False)]
    res = runner.invoke(cli, ["workflow", "list", str(proj)])
    assert res.exit_code == 0, res.output
    out = res.output
    assert out.index("workflow1") < out.index("b_inactive") < out.index("ghost") < out.index("c_orphan")
    for word in ("active", "inactive", "file missing", "invalid", "not in thread.yaml"):
        assert word in out, word


def test_list_without_thread_mentions_alphabetical(runner, proj, monkeypatch):
    (proj / "workflows" / "thread.yaml").unlink()
    monkeypatch.chdir(proj)
    res = runner.invoke(cli, ["workflow", "list"])
    assert res.exit_code == 0
    assert "alphabetical" in res.output


# ── run / validate par nom ────────────────────────────────────────────────────

def test_run_and_validate_by_name(runner, proj, monkeypatch):
    monkeypatch.chdir(proj)
    assert runner.invoke(cli, ["workflow", "validate", "workflow1"]).exit_code == 0
    res = runner.invoke(cli, ["workflow", "run", "workflow1"])
    assert res.exit_code == 0, res.output


def test_run_by_name_with_project_option(runner, proj, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    res = runner.invoke(cli, ["workflow", "validate", "workflow1", "--project", str(proj)])
    assert res.exit_code == 0, res.output


def test_workflow_init_is_gone(runner):
    res = runner.invoke(cli, ["workflow", "init", "x"])
    assert res.exit_code == 2


# ── Studio : même thread que la CLI ───────────────────────────────────────────

def test_studio_create_and_delete_update_thread(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from hydra_etl.api import store
    monkeypatch.setattr(store, "WORKSPACE", tmp_path / "ws")
    monkeypatch.setattr(store, "_INDEX_FILE", tmp_path / "ws" / "index.json")
    (tmp_path / "ws").mkdir()
    proj = store.create_project("studio proj", project_path=str(tmp_path))
    root = Path(proj.path)
    wf = store.create_workflow(proj.id, "Nightly Load", None, "manual", None)
    name = Path(wf.path).stem
    assert [w.name for s in load_thread(root / "workflows" / "thread.yaml").thread for w in s.workflows] == [name]
    store.delete_workflow(proj.id, wf.id)
    assert load_thread(root / "workflows" / "thread.yaml").workflow_names() == []


def test_studio_discovery_ignores_thread_yaml(tmp_path, monkeypatch, runner):
    pytest.importorskip("fastapi")
    from hydra_etl.api import store
    monkeypatch.setattr(store, "WORKSPACE", tmp_path / "ws")
    monkeypatch.setattr(store, "_INDEX_FILE", tmp_path / "ws" / "index.json")
    (tmp_path / "ws").mkdir()
    root = tmp_path / "cli_proj"
    runner.invoke(cli, ["init", str(root), "-q"])
    proj = store.open_project(str(root))
    names = sorted(Path(w.path).name for w in store.list_workflows(proj.id))
    assert names == ["workflow1.yaml"]
