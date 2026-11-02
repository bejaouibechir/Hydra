"""API : /api/global-env, secrets par environnement (0.18, phase C)."""
from pathlib import Path

import pytest

pytest.importorskip("fastapi")


@pytest.fixture
def api_proj(tmp_path, monkeypatch):
    from hydra_etl.api import store
    monkeypatch.setattr(store, "WORKSPACE", tmp_path / "ws")
    monkeypatch.setattr(store, "_INDEX_FILE", tmp_path / "ws" / "index.json")
    (tmp_path / "ws").mkdir()
    proj = store.create_project("p", project_path=str(tmp_path / "p"))
    return proj, Path(proj.path)


def test_global_env_crud(api_proj):
    from fastapi import HTTPException
    from hydra_etl.api.routers import global_env as r
    proj, root = api_proj
    out = r.create_env(r.CreateBody(name="prod", project_id=proj.id))
    assert [e.name for e in out.environments] == ["prod"]
    assert (root / "environments" / "prod.yaml").is_file()
    out = r.put_vars(r.VarsBody(env="prod", vars={"DB_HOST": "db.prod", "X": " spaced "}))
    assert out.environments[0].vars == {"DB_HOST": "db.prod", "X": " spaced "}
    out = r.put_vars(r.VarsBody(env=None, vars={"COMMON": "1"}))
    assert out.common.vars == {"COMMON": "1"}
    names = r.env_names(project_id=proj.id)
    assert names[0].name == "prod" and names[0].in_global and names[0].in_project
    r.rename_env("prod", r.RenameBody(new_name="production", project_id=proj.id))
    assert (root / "environments" / "production.yaml").is_file()
    out = r.delete_env("production", project_id=proj.id)
    assert out.environments == []
    with pytest.raises(HTTPException) as e:
        r.put_vars(r.VarsBody(env="prod", vars={"1BAD": "x"}))
    assert e.value.status_code == 422
    with pytest.raises(HTTPException):
        r.create_env(r.CreateBody(name="bad name"))


def test_secrets_per_environment(api_proj):
    from hydra_etl.api.routers import secrets as r
    from hydra_etl.internal.config.secrets import project_secrets
    proj, root = api_proj
    r.put_secret(r.SecretSet(project_id=proj.id, name="pw", value="common"))
    out = r.put_secret(r.SecretSet(project_id=proj.id, name="pw", value="PRODVAL", env="prod"))
    assert out.env == "prod" and out.env_file == ".hydra/secrets.prod"
    assert [(s.name, s.scope) for s in out.secrets] == [("pw", "prod")]
    assert "PRODVAL" not in out.model_dump_json()
    assert project_secrets(root, env="prod")["pw"] == "PRODVAL"
    out = r.list_secrets(project_id=proj.id)
    assert [(s.name, s.scope) for s in out.secrets] == [("pw", "common")]
    out = r.remove_secret("pw", project_id=proj.id, env="prod")
    assert [(s.name, s.scope) for s in out.secrets] == [("pw", "common")]


def test_inline_action_sees_global_env(api_proj, monkeypatch):
    import os, sys
    if sys.platform == "win32":
        pytest.skip("bash")
    from hydra_etl.api import store
    from hydra_etl.api.routers import runs as r
    from hydra_etl.internal.config.env_admin import set_global_var
    set_global_var("qa", "ONLY_QA", "yes-qa")
    run = r.RunResponse(run_id="a1", workflow_name="x", status="pending", started_at=r._now())
    store.save_run(run)
    r._execute_action_node("a1", "action_bash", "echo v=$ONLY_QA", None, 10, "x", None, "qa")
    step = store.get_run("a1").steps[0]
    assert "v=yes-qa" in ((step.get("output_text") if isinstance(step, dict) else step.output_text) or "")
    os.environ.pop("ONLY_QA", None)


def test_open_project_without_id_gets_one(tmp_path, monkeypatch):
    import json
    from hydra_etl.api import store
    monkeypatch.setattr(store, "WORKSPACE", tmp_path / "ws")
    monkeypatch.setattr(store, "_INDEX_FILE", tmp_path / "ws" / "index.json")
    (tmp_path / "ws").mkdir()
    root = tmp_path / "hand"
    (root / ".hydra").mkdir(parents=True)
    (root / "workflows").mkdir()
    (root / ".hydra" / "project.json").write_text('{"name": "hand", "description": "kept"}', encoding="utf-8")
    proj = store.open_project(str(root))
    assert proj.id and len(proj.id) == 8
    meta = json.loads((root / ".hydra" / "project.json").read_text(encoding="utf-8"))
    assert meta["id"] == proj.id and meta["description"] == "kept"
    assert store.get_project(proj.id) is not None
