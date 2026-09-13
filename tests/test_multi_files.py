"""
Sources multi-fichiers (`table: exports/*.csv`) et lecture en parallele.

Ce que l'on verifie :
- un motif lit tous les fichiers correspondants, dans l'ordre alphabetique ;
- l'ordre du resultat ne depend pas du parallelisme ;
- des en-tetes differentes sont refusees avec un message nommant le fichier ;
- un motif sans correspondance donne un message clair ;
- un chemin simple garde exactement le comportement d'avant ;
- le parallelisme ne s'active que quand il peut servir.
"""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import pytest
import yaml

from hydra_etl.internal.connector.csv_connector import CSVConnector
from hydra_etl.internal.runner.executor import JobExecutor
from hydra_etl.internal.runner.prefetch import ordered_parallel


def _fichiers(dossier: Path, nombre: int, lignes: int = 50, entete=("a", "b")) -> None:
    for i in range(nombre):
        pd.DataFrame({
            entete[0]: [i * 1000 + k for k in range(lignes)],
            entete[1]: [f"f{i}-{k}" for k in range(lignes)],
        }).to_csv(dossier / f"part{i:02d}.csv", index=False)


def _conn(dossier: Path) -> CSVConnector:
    return CSVConnector(name="s", config={"type": "csv"}, job_dir=str(dossier))


# ------------------------------------------------------------ ordered_parallel

def test_ordre_independant_des_vitesses():
    def source(i, delai):
        def lire():
            for k in range(3):
                time.sleep(delai)
                yield (i, k)
        return lire

    # la premiere source est la plus lente : l'ordre doit tenir quand meme
    sortie = list(ordered_parallel(
        [source(0, 0.03), source(1, 0.001), source(2, 0.001)], workers=3))
    assert sortie == [(i, k) for i in range(3) for k in range(3)]


def test_une_seule_source_ou_un_seul_worker():
    def source():
        yield from [1, 2, 3]

    assert list(ordered_parallel([source], workers=4)) == [1, 2, 3]
    assert list(ordered_parallel([source, source], workers=1)) == [1, 2, 3, 1, 2, 3]
    assert list(ordered_parallel([], workers=4)) == []


def test_exception_relancee_a_sa_place():
    def bonne():
        yield "ok"

    def mauvaise():
        yield "avant"
        raise RuntimeError("fichier abime")

    vus = []
    with pytest.raises(RuntimeError, match="fichier abime"):
        for x in ordered_parallel([bonne, mauvaise, bonne], workers=3):
            vus.append(x)
    assert vus == ["ok", "avant"]


def test_lecture_reellement_concurrente():
    debuts = []

    def source(i):
        def lire():
            debuts.append(time.perf_counter())
            time.sleep(0.05)
            yield i
        return lire

    list(ordered_parallel([source(i) for i in range(3)], workers=3))
    assert max(debuts) - min(debuts) < 0.04, "les sources doivent demarrer ensemble"


# --------------------------------------------------------------- motif de nom

def test_motif_lit_tous_les_fichiers_dans_l_ordre(tmp_path: Path):
    _fichiers(tmp_path, 5)
    frames = list(_conn(tmp_path).extract_frames(table=str(tmp_path / "part*.csv"),
                                                 batch_size=1000))
    total = pd.concat(frames, ignore_index=True)
    assert len(total) == 250
    assert total["a"].tolist() == [str(i * 1000 + k) for i in range(5) for k in range(50)]


def test_motif_meme_resultat_en_sequentiel_et_en_parallele(tmp_path: Path, monkeypatch):
    _fichiers(tmp_path, 6, lignes=120)
    motif = str(tmp_path / "part*.csv")

    monkeypatch.setenv("HYDRA_PARALLEL_FILES", "0")
    sequentiel = pd.concat(list(_conn(tmp_path).extract_frames(table=motif, batch_size=50)),
                           ignore_index=True)
    monkeypatch.setenv("HYDRA_PARALLEL_FILES", "1")
    parallele = pd.concat(list(_conn(tmp_path).extract_frames(table=motif, batch_size=50)),
                          ignore_index=True)
    pd.testing.assert_frame_equal(parallele, sequentiel)


def test_motif_avec_extract_batches(tmp_path: Path):
    _fichiers(tmp_path, 3, lignes=20)
    lots = list(_conn(tmp_path).extract_batches(table=str(tmp_path / "part*.csv"),
                                                batch_size=25))
    lignes = [r for lot in lots for r in lot]
    assert len(lignes) == 60
    assert lignes[0]["a"] == "0" and lignes[-1]["a"] == "2019"


def test_entetes_differentes_refusees(tmp_path: Path):
    _fichiers(tmp_path, 2)
    pd.DataFrame({"a": [1], "z": ["autre"]}).to_csv(tmp_path / "part09.csv", index=False)
    with pytest.raises(ValueError, match="en-tetes differentes"):
        list(_conn(tmp_path).extract_frames(table=str(tmp_path / "part*.csv"), batch_size=10))
    with pytest.raises(ValueError, match="part09.csv"):
        list(_conn(tmp_path).extract_batches(table=str(tmp_path / "part*.csv"), batch_size=10))


def test_motif_sans_correspondance(tmp_path: Path):
    with pytest.raises(ValueError, match="aucun fichier ne correspond au motif"):
        list(_conn(tmp_path).extract_frames(table=str(tmp_path / "rien*.csv"), batch_size=10))


def test_motif_relatif_au_dossier_du_job(tmp_path: Path):
    (tmp_path / "data").mkdir()
    _fichiers(tmp_path / "data", 3, lignes=10)
    frames = list(_conn(tmp_path).extract_frames(table="data/part*.csv", batch_size=100))
    assert sum(len(f) for f in frames) == 30


def test_chemin_simple_inchange(tmp_path: Path):
    _fichiers(tmp_path, 1, lignes=7)
    frames = list(_conn(tmp_path).extract_frames(table=str(tmp_path / "part00.csv"),
                                                 batch_size=100))
    assert sum(len(f) for f in frames) == 7


def test_estimation_sur_motif(tmp_path: Path):
    _fichiers(tmp_path, 4, lignes=100)
    per_row = _conn(tmp_path).estimate_row_bytes(str(tmp_path / "part*.csv"))
    assert per_row and per_row > 0


# ------------------------------------------------------- decision parallelisme

def test_parallelisme_desactive_par_defaut(tmp_path: Path, monkeypatch):
    """Mesure a l'appui : le consommateur est le goulot, lire plusieurs
    fichiers a la fois ne paie pas. Voir _file_workers."""
    monkeypatch.delenv("HYDRA_PARALLEL_FILES", raising=False)
    for backend in ("python", "rust"):
        monkeypatch.setenv("HYDRA_BACKEND", backend)
        assert _conn(tmp_path)._file_workers(10) == 1


def test_parallelisme_un_seul_fichier(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HYDRA_PARALLEL_FILES", "1")
    assert _conn(tmp_path)._file_workers(1) == 1


def test_parallelisme_forcable(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HYDRA_PARALLEL_FILES", "1")
    monkeypatch.setenv("HYDRA_PARALLEL_FILES_WORKERS", "3")
    assert _conn(tmp_path)._file_workers(10) == 3
    monkeypatch.setenv("HYDRA_PARALLEL_FILES", "0")
    assert _conn(tmp_path)._file_workers(10) == 1


# ------------------------------------------------------------- bout en bout

def test_job_sur_un_motif(tmp_path: Path):
    entree = tmp_path / "entree"
    entree.mkdir()
    _fichiers(entree, 5, lignes=40)

    job = tmp_path / "job"
    job.mkdir()
    (job / "sources.yaml").write_text(yaml.dump({"sources": {"s": {
        "type": "csv", "connection": {},
        "extract": {"table": str(entree / "part*.csv"), "batch_size": 100}}}}), encoding="utf-8")
    (job / "destinations.yaml").write_text(yaml.dump({"destinations": {"d": {
        "type": "csv", "connection": {},
        "load": {"table": str(job / "out.csv"), "mode": "replace"}}}}), encoding="utf-8")
    (job / "pipeline.yaml").write_text(yaml.dump({"pipeline": {"from": "s", "to": "d"}}),
                                       encoding="utf-8")
    (job / "transformations.yaml").write_text(yaml.dump({"transformations": {"steps": [
        {"cast": {"mapping": {"a": "int"}}},
        {"filter": {"expr": "a % 2 == 0"}},
        {"select": {"columns": ["a", "b"]}},
    ]}}), encoding="utf-8")

    res = JobExecutor(job_dir=job).run()
    assert res.success, res.error
    assert res.rows_in == 200
    sortie = pd.read_csv(job / "out.csv")
    assert len(sortie) == res.rows_out
    assert sortie["a"].tolist() == sorted(sortie["a"].tolist())
