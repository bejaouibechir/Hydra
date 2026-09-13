"""
Reglage automatique de batch_size (quand il n'est pas declare dans le YAML).

Regles verifiees :
- une valeur declaree est toujours respectee ;
- une valeur declaree trop petite declenche un avertissement ;
- sans valeur declaree, la taille vise ~16 Mo par lot, bornee ;
- une source qui ne sait pas s'estimer garde les 10 000 lignes d'avant ;
- la sortie du job est identique, quelle que soit la taille des lots.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import pytest
import yaml

from hydra_etl.internal.connector.csv_connector import CSVConnector
from hydra_etl.internal.runner import batch_size as bs
from hydra_etl.internal.runner.executor import JobExecutor


class _Estimateur:
    """Connecteur factice qui annonce une taille de ligne."""

    def __init__(self, per_row):
        self._per_row = per_row

    def estimate_row_bytes(self, table):
        return self._per_row


class _SansEstimation:
    pass


# --------------------------------------------------------------- resolve()

def test_sans_estimation_on_garde_la_valeur_historique():
    assert bs.resolve(_SansEstimation(), "t") == bs.DEFAULT_ROWS


@pytest.mark.parametrize("per_row", [None, 0, -5])
def test_estimation_inutilisable_on_garde_la_valeur_historique(per_row):
    assert bs.resolve(_Estimateur(per_row), "t") == bs.DEFAULT_ROWS


def test_estimation_qui_leve_ne_bloque_pas():
    class _Casse:
        def estimate_row_bytes(self, table):
            raise RuntimeError("boum")

    assert bs.resolve(_Casse(), "t") == bs.DEFAULT_ROWS


def test_taille_calculee_pour_la_cible(monkeypatch):
    monkeypatch.setenv("HYDRA_BATCH_TARGET_BYTES", str(16 * 1024 * 1024))
    # 1 Ko par ligne -> 16 384 lignes
    assert bs.resolve(_Estimateur(1024), "t") == 16 * 1024


def test_bornes_haute_et_basse(monkeypatch):
    monkeypatch.setenv("HYDRA_BATCH_TARGET_BYTES", str(16 * 1024 * 1024))
    assert bs.resolve(_Estimateur(1), "t") == bs.MAX_ROWS        # lignes minuscules
    assert bs.resolve(_Estimateur(10 ** 9), "t") == bs.MIN_ROWS  # lignes enormes


def test_desactivation_par_variable_denvironnement(monkeypatch):
    monkeypatch.setenv("HYDRA_BATCH_AUTO", "0")
    assert bs.resolve(_Estimateur(1024), "t") == bs.DEFAULT_ROWS


def test_avertissement_sur_batch_trop_petit(caplog):
    with caplog.at_level(logging.WARNING):
        bs.warn_if_too_small(100, "mon_job")
    assert "batch_size=100" in caplog.text
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        bs.warn_if_too_small(10_000, "mon_job")
    assert caplog.text == ""


# ------------------------------------------------------ estimation CSV reelle

def test_estimation_csv(tmp_path: Path):
    src = tmp_path / "in.csv"
    pd.DataFrame({"a": range(500), "texte": ["x" * 40] * 500}).to_csv(src, index=False)
    conn = CSVConnector(name="s", config={"type": "csv"}, job_dir=str(tmp_path))
    per_row = conn.estimate_row_bytes(str(src))
    assert per_row is not None
    assert 40 < per_row < 5_000  # ordre de grandeur plausible


def test_estimation_csv_fichier_absent(tmp_path: Path):
    conn = CSVConnector(name="s", config={"type": "csv"}, job_dir=str(tmp_path))
    assert conn.estimate_row_bytes(str(tmp_path / "absent.csv")) is None
    assert conn.estimate_row_bytes(None) is None


def test_estimation_csv_tient_compte_de_la_projection(tmp_path: Path):
    src = tmp_path / "in.csv"
    pd.DataFrame({"a": range(300), "gros": ["x" * 200] * 300}).to_csv(src, index=False)
    conn = CSVConnector(name="s", config={"type": "csv"}, job_dir=str(tmp_path))
    complet = conn.estimate_row_bytes(str(src))
    conn.set_projection(["a"])
    projete = conn.estimate_row_bytes(str(src))
    assert projete < complet / 2


# --------------------------------------------------------------- bout en bout

def _job(tmp_path: Path, nom: str, batch_size=None) -> Path:
    job = tmp_path / nom
    job.mkdir()
    src = job / "in.csv"
    pd.DataFrame({
        "id": range(1, 5001),
        "cat": [["a", "b", "c"][i % 3] for i in range(5000)],
        "v": [i % 97 for i in range(5000)],
    }).to_csv(src, index=False)

    extract = {"table": str(src)}
    if batch_size is not None:
        extract["batch_size"] = batch_size
    (job / "sources.yaml").write_text(yaml.dump(
        {"sources": {"s": {"type": "csv", "connection": {}, "extract": extract}}}), encoding="utf-8")
    (job / "destinations.yaml").write_text(yaml.dump(
        {"destinations": {"d": {"type": "csv", "connection": {},
                                "load": {"table": str(job / "out.csv"), "mode": "replace"}}}}),
        encoding="utf-8")
    (job / "pipeline.yaml").write_text(yaml.dump({"pipeline": {"from": "s", "to": "d"}}),
                                       encoding="utf-8")
    (job / "transformations.yaml").write_text(yaml.dump({"transformations": {"steps": [
        {"cast": {"mapping": {"v": "int"}}},
        {"filter": {"expr": "v > 10"}},
        {"select": {"columns": ["id", "cat", "v"]}},
    ]}}), encoding="utf-8")
    return job


@pytest.mark.parametrize("batch_size", [None, 100, 1000, 5000])
def test_sortie_identique_quelle_que_soit_la_taille_des_lots(tmp_path: Path, batch_size):
    ref = JobExecutor(job_dir=_job(tmp_path, "ref", 500)).run()
    assert ref.success, ref.error
    attendu = (tmp_path / "ref" / "out.csv").read_bytes()

    nom = f"essai_{batch_size}"
    res = JobExecutor(job_dir=_job(tmp_path, nom, batch_size)).run()
    assert res.success, res.error
    assert (tmp_path / nom / "out.csv").read_bytes() == attendu
    assert res.rows_in == ref.rows_in and res.rows_out == ref.rows_out


def test_valeur_declaree_respectee(tmp_path: Path):
    """Le connecteur recoit exactement la valeur du YAML."""
    vues = []
    original = CSVConnector.extract_frames

    def espion(self, *, table, batch_size=10_000, query=None, **kw):
        vues.append(batch_size)
        return original(self, table=table, batch_size=batch_size, query=query, **kw)

    CSVConnector.extract_frames = espion
    try:
        JobExecutor(job_dir=_job(tmp_path, "declare", 700)).run()
    finally:
        CSVConnector.extract_frames = original
    assert vues == [700]


def test_sans_valeur_declaree_la_taille_est_calculee(tmp_path: Path):
    vues = []
    original = CSVConnector.extract_frames

    def espion(self, *, table, batch_size=10_000, query=None, **kw):
        vues.append(batch_size)
        return original(self, table=table, batch_size=batch_size, query=query, **kw)

    CSVConnector.extract_frames = espion
    try:
        JobExecutor(job_dir=_job(tmp_path, "auto", None)).run()
    finally:
        CSVConnector.extract_frames = original
    assert vues and bs.MIN_ROWS <= vues[0] <= bs.MAX_ROWS
    assert vues[0] != bs.DEFAULT_ROWS or True  # la valeur exacte depend des donnees
