"""Step type: project — modèle, résolution, cycles (0.19, lot 1.1)."""
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from hydra_etl.workflow.models import WorkflowStep


def _project(base: Path, name: str, calls=(), extra_wf=None) -> Path:
    """Projet `name` dont le workflow `main` appelle les projets `calls`
    (liste de (valeur, options))."""
    root = base / name
    (root / ".hydra").mkdir(parents=True)
    (root / ".hydra" / "project.json").write_text(json.dumps({"id": name[:8], "name": name}))
    (root / "workflows").mkdir()
    steps = ["    - name: hello\n      type: action\n      action: log\n      params: {message: hi}\n"]
    for i, (value, opts) in enumerate(calls):
        o = "".join(f"      {k}: {json.dumps(v)}\n" for k, v in opts.items())
        steps.append(f"    - name: call{i}\n      type: project\n      project: {value}\n{o}")
    (root / "workflows" / "main.yaml").write_text("workflow:\n  name: main\n  steps:\n" + "".join(steps))
    (root / "workflows" / "thread.yaml").write_text(
        "thread:\n  - mode: sequential\n    workflows:\n      - name: main\n")
    if extra_wf:
        (root / "workflows" / f"{extra_wf[0]}.yaml").write_text(extra_wf[1])
    return root


# ── Modèle ────────────────────────────────────────────────────────────────

def test_model_accepts_a_project_step():
    s = WorkflowStep(name="a", type="project", project="../crm", env="inherit",
                     params={"run_date": "{{ param:d }}"}, variables={"API_URL": "x"},
                     workflows=["daily"], outputs=["last_id"], isolation="subprocess", ref="path")
    assert s.type == "project" and s.ref == "path"


@pytest.mark.parametrize("kw, msg", [
    (dict(type="project"), "requires the 'project' field"),
    (dict(type="project", project="p", job="j"), "'job' applies to type=job"),
    (dict(type="project", project="p", env="bad env"), "env 'bad env'"),
    (dict(type="project", project="p", params={"pw": "${SECRET:db.pw}"}), "keeps its own secrets"),
    (dict(type="project", project="p", variables={"PW": "${SECRET:db.pw}"}), "keeps its own secrets"),
    (dict(type="project", project="p", variables={"1X": "a"}), "invalid variable name"),
    (dict(type="project", project="p", workflows=[]), "workflows is empty"),
    (dict(type="project", project="p", undo="none"), "'undo' applies to type=action"),
    (dict(type="job", job="j", env="dev"), "env applies to type=project"),
    (dict(type="action", action="log", project="p"), "project applies to type=project"),
    (dict(type="project", project="p", secrets={"a": "b"}), "secrets"),
])
def test_model_rejects(kw, msg):
    with pytest.raises(Exception) as e:
        WorkflowStep(name="a", **kw)
    assert msg in str(e.value)


# ── Résolution ─────────────────────────────────────────────────────────────

def test_resolve_by_path_and_errors(tmp_path):
    from hydra_etl.workflow.subprojects import ProjectRefError, resolve_project
    master = _project(tmp_path, "master")
    slave = _project(tmp_path, "slave")
    assert resolve_project("../slave", master) == slave.resolve()
    with pytest.raises(ProjectRefError, match="not found"):
        resolve_project("../nope", master)
    (tmp_path / "plain").mkdir()
    with pytest.raises(ProjectRefError, match="not a Hydra project"):
        resolve_project("../plain", master)


def test_resolve_by_name_in_the_workspace(tmp_path, monkeypatch):
    from hydra_etl.workflow.subprojects import ProjectRefError, resolve_project
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("HYDRA_WORKSPACE", str(ws))
    master = _project(tmp_path, "master")
    elsewhere = _project(tmp_path / "far", "crm-sync")
    (ws / "projects.index.json").write_text(json.dumps({"x1": str(elsewhere)}))
    assert resolve_project("crm-sync", master, "name") == elsewhere.resolve()
    with pytest.raises(ProjectRefError, match="no project named"):
        resolve_project("unknown", master, "name")
    _project(ws, "crm-sync")                    # même nom, dans le workspace
    with pytest.raises(ProjectRefError, match="several projects"):
        resolve_project("crm-sync", master, "name")


# ── Cycles et profondeur ───────────────────────────────────────────────────

def test_no_cycle_tree(tmp_path):
    from hydra_etl.workflow.subprojects import check_project_calls
    _project(tmp_path, "c")
    _project(tmp_path, "b", calls=[("../c", {})])
    a = _project(tmp_path, "a", calls=[("../b", {}), ("../c", {})])
    r = check_project_calls(a)
    assert r.errors == []
    assert [lbl for _, lbl in r.tree] == ["b", "c", "c"]


def test_cycle_a_b_a(tmp_path):
    from hydra_etl.workflow.project import ProjectError, prepare_project
    _project(tmp_path, "b", calls=[("../a", {})])
    a = _project(tmp_path, "a", calls=[("../b", {})])
    with pytest.raises(ProjectError) as e:
        prepare_project(a)
    assert any("cycle: a → b → a" in m for m in e.value.errors)


def test_project_calls_itself(tmp_path):
    from hydra_etl.workflow.subprojects import check_project_calls
    a = _project(tmp_path, "a", calls=[(".", {})])
    assert any("calls itself" in m for m in check_project_calls(a).errors)


def test_long_cycle_and_depth(tmp_path):
    from hydra_etl.workflow.subprojects import check_project_calls
    _project(tmp_path, "c", calls=[("../a", {})])
    _project(tmp_path, "b", calls=[("../c", {})])
    a = _project(tmp_path, "a", calls=[("../b", {})])
    assert any("cycle: a → b → c → a" in m for m in check_project_calls(a).errors)
    # chaîne p0 → p1 → … → p6 : plus de 5 niveaux
    _project(tmp_path, "p6")
    for i in range(5, -1, -1):
        _project(tmp_path, f"p{i}", calls=[(f"../p{i + 1}", {})])
    errs = check_project_calls(tmp_path / "p0").errors
    assert any("more than 5 levels" in m for m in errs)


def test_only_the_called_workflows_count(tmp_path):
    """b.other appelle a, mais a ne lance que b.main : pas de cycle."""
    from hydra_etl.workflow.subprojects import check_project_calls
    other = "workflow:\n  name: other\n  steps:\n    - name: back\n      type: project\n      project: ../a\n"
    _project(tmp_path, "b", extra_wf=("other", other))
    a = _project(tmp_path, "a", calls=[("../b", {"workflows": ["main"]})])
    assert check_project_calls(a).errors == []
    a2 = _project(tmp_path, "a2", calls=[("../b", {"workflows": ["other"]})])
    assert check_project_calls(a2).errors == []        # other appelle a, pas a2
    a3 = _project(tmp_path / "x", "a", calls=[("../../b", {"workflows": ["other"]})])
    assert check_project_calls(a3).errors == []        # ../a depuis b n'est pas x/a


def test_missing_and_dynamic_reference(tmp_path):
    from hydra_etl.workflow.project import ProjectError, prepare_project
    from hydra_etl.workflow.subprojects import check_project_calls
    a = _project(tmp_path, "a", calls=[("../ghost", {})])
    with pytest.raises(ProjectError) as e:
        prepare_project(a)
    assert any("project folder not found" in m for m in e.value.errors)
    d = _project(tmp_path, "d", calls=[("'../{{ param:target }}'", {})])
    r = check_project_calls(d)
    assert r.errors == [] and any("computed at run time" in m for m in r.warnings)


def test_rollback_refuses_a_project_step(tmp_path):
    from hydra_etl.workflow.parser import load_workflow
    from hydra_etl.workflow.rollback import rollback_problems
    _project(tmp_path, "b")
    a = _project(tmp_path, "a", calls=[("../b", {})])
    f = a / "workflows" / "main.yaml"
    f.write_text(f.read_text().replace("  name: main\n", "  name: main\n  rollback: true\n"))
    probs = rollback_problems(load_workflow(f), f.parent)
    assert any("cannot be undone" in p for p in probs)


def test_cli_workflow_validate_reports_the_cycle(tmp_path):
    from hydra_etl.cli.hdrctl import cli
    _project(tmp_path, "b", calls=[("../a", {})])
    a = _project(tmp_path, "a", calls=[("../b", {})])
    r = CliRunner().invoke(cli, ["workflow", "validate", "main", "--project", str(a)])
    assert r.exit_code == 1 and "cycle: a → b → a" in r.output
    _project(tmp_path, "z")
    ok = _project(tmp_path, "y", calls=[("../z", {})])
    r = CliRunner().invoke(cli, ["workflow", "validate", "main", "--project", str(ok)])
    assert r.exit_code == 0, r.output
    assert "↳ z" in r.output
