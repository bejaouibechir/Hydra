"""
Tests du profil d'execution (--profile / HYDRA_PROFILE=1).

Ce que l'on verifie :
- desactive par defaut : aucun surcout, result.profile est None ;
- active : chaque etape du pipeline apparait, avec extract et load ;
- la somme des temps mesures ne depasse pas la duree du job ;
- l'activation par variable d'environnement fonctionne.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from hydra_etl.internal.runner.executor import JobExecutor
from hydra_etl.internal.runner.profiler import (
    JobProfiler,
    format_profile,
    profile_enabled,
)


def _job(tmp_path: Path) -> Path:
    job = tmp_path / "job"
    job.mkdir()
    src = job / "in.csv"
    pd.DataFrame(
        {"id": [1, 2, 3, 4], "value": [10, 20, 30, 40], "keep": ["y", "n", "y", "y"]}
    ).to_csv(src, index=False)

    (job / "sources.yaml").write_text(yaml.dump({
        "sources": {"s": {"type": "csv", "connection": {},
                          "extract": {"table": str(src), "batch_size": 1000}}}
    }), encoding="utf-8")
    (job / "destinations.yaml").write_text(yaml.dump({
        "destinations": {"d": {"type": "csv", "connection": {},
                               "load": {"table": str(job / "out.csv"), "mode": "replace"}}}
    }), encoding="utf-8")
    (job / "pipeline.yaml").write_text(yaml.dump({"pipeline": {"from": "s", "to": "d"}}),
                                       encoding="utf-8")
    (job / "transformations.yaml").write_text(yaml.dump({
        "transformations": {"steps": [
            {"cast": {"mapping": {"value": "int"}}},
            {"filter": {"expr": "keep == 'y'"}},
            {"calculate": {"column": "double", "expr": "value * 2"}},
        ]}
    }), encoding="utf-8")
    return job


# --------------------------------------------------------------- profiler nu

def test_profiler_disabled_collects_nothing():
    p = JobProfiler(enabled=False)
    with p.span("x"):
        pass
    p.add("y", 1.0)
    assert list(p.iterate("z", [1, 2, 3])) == [1, 2, 3]
    assert p.to_dict(total=1.0)["entries"] == []


def test_profiler_enabled_orders_and_counts():
    p = JobProfiler(enabled=True)
    p.add("extract", 0.5)
    p.add("load", 0.25)
    p.add("extract", 0.5)
    d = p.to_dict(total=2.0, rows_in=10, rows_out=8, job_id="j")
    labels = [e["label"] for e in d["entries"]]
    assert labels[:2] == ["extract", "load"]
    assert d["entries"][0]["seconds"] == 1.0
    assert d["entries"][0]["calls"] == 2
    assert abs(d["entries"][0]["share"] - 0.5) < 1e-9
    # le temps non mesure apparait comme reste
    assert labels[-1].startswith("(reste")
    assert "extract" in format_profile(d)


def test_profile_enabled_from_env(monkeypatch):
    monkeypatch.delenv("HYDRA_PROFILE", raising=False)
    assert profile_enabled() is False
    monkeypatch.setenv("HYDRA_PROFILE", "1")
    assert profile_enabled() is True
    # un argument explicite l'emporte sur l'environnement
    assert profile_enabled(False) is False


# ----------------------------------------------------------------- executor

def test_executor_without_profile_returns_none(tmp_path: Path):
    res = JobExecutor(job_dir=_job(tmp_path)).run()
    assert res.success, res.error
    assert res.profile is None


def test_executor_profile_lists_every_step(tmp_path: Path):
    res = JobExecutor(job_dir=_job(tmp_path), profile=True).run()
    assert res.success, res.error
    assert res.profile is not None

    labels = [e["label"] for e in res.profile["entries"]]
    assert "extract" in labels
    assert "load" in labels
    assert "1 cast" in labels
    assert "2 filter" in labels
    assert "3 calculate" in labels

    assert res.profile["rows_in"] == 4
    assert res.profile["rows_out"] == 3
    measured = sum(e["seconds"] for e in res.profile["entries"])
    # le reste est calcule pour que le total colle a la duree du job
    assert measured <= res.profile["total"] + 1e-3


def test_executor_profile_via_env(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HYDRA_PROFILE", "true")
    res = JobExecutor(job_dir=_job(tmp_path)).run()
    assert res.success, res.error
    assert res.profile is not None


def test_profile_present_on_failure(tmp_path: Path):
    job = _job(tmp_path)
    (job / "transformations.yaml").write_text(yaml.dump({
        "transformations": {"steps": [{"select": {"columns": ["colonne_absente"]}}]}
    }), encoding="utf-8")
    res = JobExecutor(job_dir=job, profile=True).run()
    assert res.success is False
    assert res.profile is not None
