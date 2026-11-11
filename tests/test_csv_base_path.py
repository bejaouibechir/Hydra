"""A relative base_path starts from the project root (.hydra/project.json), or from the job
folder outside a project; the old rule (current folder) still works, with a warning."""
from __future__ import annotations

import logging
from pathlib import Path

from hydra_etl.internal.connector.csv_connector import CSVConnector


def _base(config_base: str, job_dir: Path) -> Path:
    c = CSVConnector._normalize_settings({"connection": {"base_path": config_base}}, job_dir)
    return Path(c.base_path)


def test_from_the_project_root(tmp_path):
    (tmp_path / ".hydra").mkdir()
    (tmp_path / ".hydra" / "project.json").write_text("{}", encoding="utf-8")
    (tmp_path / "imports" / "supplier").mkdir(parents=True)
    job = tmp_path / "jobs" / "a" / "b"
    job.mkdir(parents=True)
    assert _base("imports/supplier", job) == (tmp_path / "imports" / "supplier").resolve()


def test_from_the_job_folder_outside_a_project(tmp_path):
    job = tmp_path / "job"
    (job / "in").mkdir(parents=True)
    assert _base("in", job) == (job / "in").resolve()


def test_home_hydra_folder_is_not_a_project(tmp_path):
    (tmp_path / ".hydra").mkdir()           # like ~/.hydra: settings, no project.json
    job = tmp_path / "job"
    (job / "in").mkdir(parents=True)
    assert _base("in", job) == (job / "in").resolve()


def test_absolute_base_path_is_kept(tmp_path):
    other = tmp_path / "elsewhere"
    other.mkdir()
    assert _base(str(other), tmp_path) == other.resolve()


def test_old_rule_still_works_with_a_warning(tmp_path, monkeypatch, caplog):
    (tmp_path / "legacy").mkdir()
    job = tmp_path / "x" / "job"
    job.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    with caplog.at_level(logging.WARNING):
        assert _base("legacy", job) == (tmp_path / "legacy").resolve()
    assert "current folder" in caplog.text
