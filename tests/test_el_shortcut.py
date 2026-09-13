"""
Court-circuit des jobs purement E-L (aucune transformation).

Sans transformation, le chemin historique construit un dict par ligne a la
lecture puis le relit ligne par ligne a l'ecriture. Quand les deux bouts
sont "par colonnes" (lecteur et ecrivain natifs), on peut passer le lot en
DataFrame et supprimer ces deux conversions. Quand ils ne le sont pas, le
faire couterait plus cher : le court-circuit doit alors rester inactif.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import yaml

from hydra_etl._backend import native_status
from hydra_etl.internal.connector.csv_connector import CSVConnector
from hydra_etl.internal.runner.executor import JobExecutor

_NATIF, _RAISON = native_status()


def _job(tmp_path: Path, nom: str, steps=None) -> Path:
    job = tmp_path / nom
    job.mkdir()
    src = job / "in.csv"
    pd.DataFrame({
        "id": range(1, 2001),
        "nom": [f"client {i}" for i in range(2000)],
        "montant": [round(i * 1.37, 2) for i in range(2000)],
        "note": ["texte, avec virgule" if i % 5 else 'guillemet "double"' for i in range(2000)],
    }).to_csv(src, index=False)

    (job / "sources.yaml").write_text(yaml.dump(
        {"sources": {"s": {"type": "csv", "connection": {},
                           "extract": {"table": str(src), "batch_size": 500}}}}), encoding="utf-8")
    (job / "destinations.yaml").write_text(yaml.dump(
        {"destinations": {"d": {"type": "csv", "connection": {},
                                "load": {"table": str(job / "out.csv"), "mode": "replace"}}}}),
        encoding="utf-8")
    (job / "pipeline.yaml").write_text(yaml.dump({"pipeline": {"from": "s", "to": "d"}}),
                                       encoding="utf-8")
    (job / "transformations.yaml").write_text(
        yaml.dump({"transformations": {"steps": steps or []}}), encoding="utf-8")
    return job


# --------------------------------------------------------------- decision

class _Colonnes:
    def reader_is_columnar(self, table=None):
        return True

    def writer_is_columnar(self, table=None):
        return True


class _Lignes:
    def reader_is_columnar(self, table=None):
        return False

    def writer_is_columnar(self, table=None):
        return False


class _Casse:
    def reader_is_columnar(self, table=None):
        raise RuntimeError("boum")


def test_interrogation_des_capacites():
    assert JobExecutor._columnar(_Colonnes(), "reader_is_columnar", "t") is True
    assert JobExecutor._columnar(_Lignes(), "writer_is_columnar", "t") is False
    assert JobExecutor._columnar(object(), "reader_is_columnar", "t") is False
    assert JobExecutor._columnar(_Casse(), "reader_is_columnar", "t") is False


def test_csv_annonce_ses_capacites_selon_le_backend(monkeypatch, tmp_path):
    conn = CSVConnector(name="s", config={"type": "csv"}, job_dir=str(tmp_path))
    monkeypatch.setenv("HYDRA_BACKEND", "python")
    assert conn.reader_is_columnar() is False
    assert conn.writer_is_columnar() is False
    monkeypatch.setenv("HYDRA_BACKEND", "rust")
    attendu = _NATIF
    assert conn.reader_is_columnar() is attendu
    assert conn.writer_is_columnar() is attendu


# ------------------------------------------------------- parite de la sortie

@pytest.mark.parametrize("backend", ["python", "rust"])
def test_sortie_identique_avec_et_sans_court_circuit(tmp_path: Path, backend, monkeypatch):
    if backend == "rust" and not _NATIF:
        pytest.skip(f"module natif absent : {_RAISON}")
    monkeypatch.setenv("HYDRA_BACKEND", backend)

    monkeypatch.setenv("HYDRA_FRAME_IO", "0")
    ref = JobExecutor(job_dir=_job(tmp_path, f"ref_{backend}")).run()
    assert ref.success, ref.error
    attendu = (tmp_path / f"ref_{backend}" / "out.csv").read_bytes()

    monkeypatch.setenv("HYDRA_FRAME_IO", "1")
    res = JobExecutor(job_dir=_job(tmp_path, f"new_{backend}")).run()
    assert res.success, res.error
    assert (tmp_path / f"new_{backend}" / "out.csv").read_bytes() == attendu
    assert (res.rows_in, res.rows_out) == (ref.rows_in, ref.rows_out)
    assert res.output_columns == ref.output_columns
    assert res.output_sample == ref.output_sample


# --------------------------------------------------- chemin effectivement pris

def _chemins_utilises(job: Path):
    """(extract_frames appele ?, extract_batches appele ?)"""
    vus = {"frames": False, "batches": False}
    of, ob = CSVConnector.extract_frames, CSVConnector.extract_batches

    def spy_f(self, **kw):
        vus["frames"] = True
        return of(self, **kw)

    def spy_b(self, **kw):
        vus["batches"] = True
        return ob(self, **kw)

    CSVConnector.extract_frames, CSVConnector.extract_batches = spy_f, spy_b
    try:
        res = JobExecutor(job_dir=job).run()
    finally:
        CSVConnector.extract_frames, CSVConnector.extract_batches = of, ob
    assert res.success, res.error
    return vus


def test_el_pur_en_tout_python_garde_le_chemin_historique(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HYDRA_BACKEND", "python")
    vus = _chemins_utilises(_job(tmp_path, "py"))
    assert vus["batches"] is True and vus["frames"] is False


@pytest.mark.skipif(not _NATIF, reason="module natif absent")
def test_el_pur_en_natif_prend_le_court_circuit(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HYDRA_BACKEND", "rust")
    vus = _chemins_utilises(_job(tmp_path, "rs"))
    assert vus["frames"] is True and vus["batches"] is False


def test_avec_transformation_le_chemin_dataframe_reste_actif(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HYDRA_BACKEND", "python")
    job = _job(tmp_path, "avec_steps", steps=[{"select": {"columns": ["id", "nom"]}}])
    vus = _chemins_utilises(job)
    assert vus["frames"] is True
