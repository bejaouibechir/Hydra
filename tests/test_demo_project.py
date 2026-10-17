"""Projet de démo livré avec le package : installation, chemins, exécution."""
import pytest

from hydra_etl.api import demo, store


@pytest.fixture
def ws(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "WORKSPACE", tmp_path)
    monkeypatch.setattr(store, "_INDEX_FILE", tmp_path / "projects.index.json")
    monkeypatch.setattr(store, "_HIDDEN_FILE", tmp_path / "projects.hidden.json")
    monkeypatch.delenv("HYDRA_NO_DEMO", raising=False)
    return tmp_path


def test_seed_once(ws):
    p = demo.seed_on_first_run()
    assert p is not None
    assert (ws / "hydra-demo" / "Data" / "orders_raw.csv").is_file()
    assert demo.seed_on_first_run() is None          # pas de 2e fois
    store.delete_project(p.id, remove_files=True)
    assert demo.seed_on_first_run() is None          # jamais recréée


def test_paths_rewritten(ws):
    demo.install_demo_project()
    txt = (ws / "hydra-demo" / "jobs" / "clean-orders" / "sources.yaml").read_text()
    assert "__HYDRA_DEMO_ROOT__" not in txt
    assert (ws / "hydra-demo").resolve().as_posix() in txt


def test_no_seed_when_projects_exist(ws):
    store.create_project("mine")
    assert demo.seed_on_first_run() is None


def test_opt_out(ws, monkeypatch):
    monkeypatch.setenv("HYDRA_NO_DEMO", "1")
    assert demo.seed_on_first_run() is None


def test_button_twice_makes_copy(ws):
    a = demo.install_demo_project()
    b = demo.install_demo_project()
    assert a.path != b.path


def test_jobs_registered(ws):
    p = demo.install_demo_project()
    assert len(store.list_workflows(p.id)) >= 1
