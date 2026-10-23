"""Studio ↔ disque : un fichier modifié hors de Studio (CLI, éditeur) depuis
la dernière sauvegarde est signalé au GET et n'est jamais écrasé par un PUT
sans confirmation (409)."""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

pytest.importorskip("fastapi", reason="l'extra [server] n'est pas installe")

from fastapi import HTTPException  # noqa: E402

from hydra_etl.api import store  # noqa: E402
from hydra_etl.workflow.jobs import attach_job, create_job  # noqa: E402

WF_YAML = 'version: "1.0"\nworkflow:\n  name: wf\n  steps:\n    - {name: j, type: job, job: ../jobs/j}\n'
JOB = {"name": "j", "sources": "sources: {}\n", "transformations": "steps: []\n",
       "destinations": "destinations: {}\n", "pipeline": "pipeline: {}\n"}
LAYOUT = {"nodes": [{"id": "n1"}], "edges": [], "job_canvases": {"j": {"nodes": [], "edges": []}},
          "job_names": {"j": "j"}}


@pytest.fixture
def studio(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "WORKSPACE", tmp_path / "ws")
    monkeypatch.setattr(store, "_INDEX_FILE", tmp_path / "ws" / "index.json")
    (tmp_path / "ws").mkdir()
    proj = store.create_project("p", project_path=str(tmp_path))
    wf = store.create_workflow(proj.id, "wf", None, "manual", None)
    saved = store.update_workflow(proj.id, wf.id, {"layout": LAYOUT, "yaml_content": WF_YAML, "jobs": [JOB]})
    return proj, wf, Path(proj.path), saved


def test_save_records_hashes_and_get_is_clean(studio):
    proj, wf, root, saved = studio
    assert set(saved.disk_hashes) == {"workflows/wf.yaml", "jobs/j/sources.yaml", "jobs/j/transformations.yaml",
                                      "jobs/j/destinations.yaml", "jobs/j/pipeline.yaml"}
    got = store.get_workflow(proj.id, wf.id)
    assert got.external_changes is None
    assert got.disk_state == saved.disk_hashes
    # Les champs calculés ne sont pas persistés dans la méta
    meta = (root / ".hydra" / "workflows" / f"{wf.id}.json").read_text(encoding="utf-8")
    assert "external_changes" not in meta and "disk_state" not in meta and "disk_hashes" in meta


def test_cli_change_is_reported_and_blocks_blind_save(studio):
    proj, wf, root, _ = studio
    create_job(root, "k")
    attach_job(root, "k", "wf")                                   # hdrctl job attach k wf
    got = store.get_workflow(proj.id, wf.id)
    assert got.external_changes == ["workflows/wf.yaml"]
    assert "jobs/k/pipeline.yaml" in got.disk_state                # job cité par le YAML
    with pytest.raises(store.WorkflowConflict) as e:
        store.update_workflow(proj.id, wf.id, {"layout": LAYOUT, "yaml_content": WF_YAML, "jobs": [JOB]})
    assert e.value.files == ["workflows/wf.yaml"]
    assert "jobs/k" in (root / "workflows" / "wf.yaml").read_text(encoding="utf-8")   # rien écrasé


def test_save_based_on_fresh_disk_state_passes(studio):
    proj, wf, root, _ = studio
    (root / "workflows" / "wf.yaml").write_text(WF_YAML + "# edited\n", encoding="utf-8")
    fresh = store.get_workflow(proj.id, wf.id)                    # Studio recharge depuis le disque
    new_yaml = WF_YAML.replace("name: wf", "name: wf2")
    out = store.update_workflow(proj.id, wf.id, {"layout": LAYOUT, "yaml_content": new_yaml,
                                                 "jobs": [JOB], "base_disk": fresh.disk_state})
    assert (root / "workflows" / "wf.yaml").read_text(encoding="utf-8") == new_yaml
    assert store.get_workflow(proj.id, wf.id).external_changes is None
    assert out.disk_state["workflows/wf.yaml"] == store._sha256(root / "workflows" / "wf.yaml")


def test_stale_base_conflicts_on_job_file(studio):
    proj, wf, root, saved = studio
    base = dict(saved.disk_state)
    (root / "jobs" / "j" / "sources.yaml").write_text("sources: {changed: 1}\n", encoding="utf-8")
    with pytest.raises(store.WorkflowConflict) as e:
        store.update_workflow(proj.id, wf.id, {"layout": LAYOUT, "yaml_content": WF_YAML,
                                               "jobs": [JOB], "base_disk": base})
    assert e.value.files == ["jobs/j/sources.yaml"]


def test_force_overwrites(studio):
    proj, wf, root, _ = studio
    (root / "workflows" / "wf.yaml").write_text("workflow: {name: x, steps: []}\n", encoding="utf-8")
    store.update_workflow(proj.id, wf.id, {"layout": LAYOUT, "yaml_content": WF_YAML, "jobs": [JOB], "force": True})
    assert (root / "workflows" / "wf.yaml").read_text(encoding="utf-8") == WF_YAML
    assert store.get_workflow(proj.id, wf.id).external_changes is None


def test_new_job_folder_not_known_at_load_conflicts(studio):
    proj, wf, root, saved = studio
    base = dict(saved.disk_state)
    (root / "jobs" / "new").mkdir()
    (root / "jobs" / "new" / "pipeline.yaml").write_text("pipeline: {}\n", encoding="utf-8")
    job_new = dict(JOB, name="new")
    with pytest.raises(store.WorkflowConflict) as e:
        store.update_workflow(proj.id, wf.id, {"layout": LAYOUT, "yaml_content": WF_YAML,
                                               "jobs": [JOB, job_new], "base_disk": base})
    assert e.value.files == ["jobs/new/pipeline.yaml"]


def test_legacy_meta_uses_modification_time(studio):
    proj, wf, root, _ = studio
    meta = root / ".hydra" / "workflows" / f"{wf.id}.json"
    data = store._read_wf_meta(root, wf.id)
    data.pop("disk_hashes", None)
    meta.write_text(store.WorkflowResponse(**data).model_dump_json(exclude={"disk_hashes"}), encoding="utf-8")
    assert store.get_workflow(proj.id, wf.id).external_changes is None
    f = root / "workflows" / "wf.yaml"
    later = time.time() + 60
    os.utime(f, (later, later))
    assert store.get_workflow(proj.id, wf.id).external_changes == ["workflows/wf.yaml"]


def test_never_drawn_workflow_has_no_external_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "WORKSPACE", tmp_path / "ws")
    monkeypatch.setattr(store, "_INDEX_FILE", tmp_path / "ws" / "index.json")
    (tmp_path / "ws").mkdir()
    proj = store.create_project("p", project_path=str(tmp_path))
    wf = store.create_workflow(proj.id, "wf", None, "manual", None)
    (Path(proj.path) / "workflows" / "wf.yaml").write_text(WF_YAML, encoding="utf-8")
    assert store.get_workflow(proj.id, wf.id).external_changes is None


def test_trigger_only_patch_still_updates_yaml(studio):
    proj, wf, root, _ = studio
    store.update_workflow(proj.id, wf.id, {"trigger_type": "schedule", "cron": "0 6 * * *"})
    assert "0 6 * * *" in (root / "workflows" / "wf.yaml").read_text(encoding="utf-8")
    # Retouche faite par Studio lui-même : pas un changement externe.
    assert store.get_workflow(proj.id, wf.id).external_changes is None


def test_trigger_patch_keeps_a_real_external_change_visible(studio):
    proj, wf, root, _ = studio
    (root / "workflows" / "wf.yaml").write_text(WF_YAML + "# cli\n", encoding="utf-8")
    store.update_workflow(proj.id, wf.id, {"trigger_type": "webhook"})
    assert store.get_workflow(proj.id, wf.id).external_changes == ["workflows/wf.yaml"]


def test_router_returns_409_with_files(studio):
    from hydra_etl.api.models import WorkflowUpdate
    from hydra_etl.api.routers import workflows as r
    proj, wf, root, _ = studio
    (root / "workflows" / "wf.yaml").write_text("workflow: {name: x, steps: []}\n", encoding="utf-8")
    with pytest.raises(HTTPException) as e:
        r.update_workflow(wf.id, WorkflowUpdate(layout=LAYOUT, yaml_content=WF_YAML), project_id=proj.id)
    assert e.value.status_code == 409
    assert e.value.detail["files"] == ["workflows/wf.yaml"]


# ── Synchronisation d'un job (bouton Sync / rafraîchissement automatique) ─────

def test_job_files_report_disk_state(studio):
    """GET /api/jobs/files : empreintes par fichier, empreinte globale, date."""
    from fastapi.testclient import TestClient
    import hydra_etl.api.main as main
    proj, _, root, _ = studio
    client = TestClient(main.app)
    d = client.get(f"/api/jobs/files?project_id={proj.id}&name=j").json()
    assert set(d["hashes"]) == {"jobs/j/sources.yaml", "jobs/j/transformations.yaml",
                                "jobs/j/destinations.yaml", "jobs/j/pipeline.yaml"}
    assert d["hash"] and d["mtime"] > 0
    time.sleep(0.01)
    (root / "jobs" / "j" / "sources.yaml").write_text("sources: {a: {type: csv}}\n", encoding="utf-8")
    d2 = client.get(f"/api/jobs/files?project_id={proj.id}&name=j").json()
    assert d2["hash"] != d["hash"]
    assert d2["hashes"]["jobs/j/sources.yaml"] != d["hashes"]["jobs/j/sources.yaml"]
    assert d2["hashes"]["jobs/j/pipeline.yaml"] == d["hashes"]["jobs/j/pipeline.yaml"]


def test_partial_job_save_keeps_other_hashes(studio):
    """Une sauvegarde d'un seul job (Sync) garde l'empreinte du workflow : un
    changement externe du workflow reste détecté."""
    proj, wf, root, _ = studio
    job = dict(JOB, sources="sources: {b: {type: csv}}\n")
    saved = store.update_workflow(proj.id, wf.id, {"layout": LAYOUT, "jobs": [job], "force": True})
    assert "workflows/wf.yaml" in saved.disk_hashes
    (root / "workflows" / "wf.yaml").write_text(WF_YAML + "# edited\n", encoding="utf-8")
    assert store.get_workflow(proj.id, wf.id).external_changes == ["workflows/wf.yaml"]
