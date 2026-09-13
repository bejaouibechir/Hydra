"""
Parquet comme format des sorties intermediaires.

Ce que l'on verifie :
- lecture en DataFrame (extract_frames) identique au chemin par dicts ;
- ecriture en flux : contenu identique a l'ancienne ecriture en un bloc ;
- append : les lignes existantes sont conservees, schema verifie ;
- rien n'est laisse derriere en cas d'echec (pas de fichier temporaire, et
  le fichier d'origine reste intact) ;
- projection de colonnes a la lecture ;
- chaine de jobs CSV -> Parquet -> CSV identique a CSV -> CSV.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import yaml

pytest.importorskip("pyarrow")
import pyarrow.parquet as pq  # noqa: E402

from hydra_etl.internal.connector.frame_batch import FrameBatch  # noqa: E402
from hydra_etl.internal.connector.parquet_connector import ParquetConnector  # noqa: E402
from hydra_etl.internal.runner.executor import JobExecutor  # noqa: E402


def _conn(tmp_path: Path) -> ParquetConnector:
    return ParquetConnector(name="test", config={"type": "parquet"}, job_dir=str(tmp_path))


def _donnees(n: int = 2500) -> pd.DataFrame:
    return pd.DataFrame({
        "id": range(n),
        "cat": [["a", "b", "c"][i % 3] for i in range(n)],
        "montant": [round(i * 1.5, 2) for i in range(n)],
        "note": [f"ligne {i}" for i in range(n)],
    })


# ------------------------------------------------------------------ lecture

def test_extract_frames_egale_le_chemin_par_dicts(tmp_path: Path):
    f = tmp_path / "src.parquet"
    _donnees().to_parquet(f, index=False)
    conn = _conn(tmp_path)

    par_dicts = pd.DataFrame(
        [r for b in conn.extract_batches(table=str(f), batch_size=700) for r in b]
    )
    par_frames = pd.concat(
        list(conn.extract_frames(table=str(f), batch_size=700)), ignore_index=True
    )
    pd.testing.assert_frame_equal(par_frames, par_dicts)


def test_projection_a_la_lecture(tmp_path: Path):
    f = tmp_path / "src.parquet"
    _donnees(100).to_parquet(f, index=False)
    conn = _conn(tmp_path)
    conn.set_projection(["id", "montant"])
    frames = list(conn.extract_frames(table=str(f), batch_size=1000))
    assert [list(x.columns) for x in frames] == [["id", "montant"]]

    conn.set_projection(["id", "colonne_absente"])
    frames = list(conn.extract_frames(table=str(f), batch_size=1000))
    assert [list(x.columns) for x in frames] == [["id"]]


def test_estimation_de_la_taille_de_ligne(tmp_path: Path):
    f = tmp_path / "src.parquet"
    _donnees(5000).to_parquet(f, index=False)
    per_row = _conn(tmp_path).estimate_row_bytes(str(f))
    assert per_row and 1 < per_row < 10_000


# ----------------------------------------------------------------- ecriture

def test_ecriture_en_flux_contenu_identique(tmp_path: Path):
    df = _donnees(3000)
    attendu = tmp_path / "attendu.parquet"
    df.to_parquet(attendu, index=False)

    obtenu = tmp_path / "obtenu.parquet"
    lots = [df.iloc[i:i + 500].to_dict(orient="records") for i in range(0, len(df), 500)]
    _conn(tmp_path).load_batches(lots, table=str(obtenu), mode="replace")

    pd.testing.assert_frame_equal(pd.read_parquet(obtenu), pd.read_parquet(attendu))


def test_ecriture_depuis_des_frame_batch(tmp_path: Path):
    df = _donnees(1200)
    cible = tmp_path / "out.parquet"
    lots = [FrameBatch.wrap(df.iloc[i:i + 400].reset_index(drop=True))
            for i in range(0, len(df), 400)]
    assert all(lot is not None for lot in lots)
    _conn(tmp_path).load_batches(lots, table=str(cible), mode="replace")
    pd.testing.assert_frame_equal(pd.read_parquet(cible), df)


def test_plusieurs_lots_donnent_plusieurs_groupes_de_lignes(tmp_path: Path):
    """Preuve que l'ecriture est bien en flux et non accumulee."""
    df = _donnees(3000)
    cible = tmp_path / "out.parquet"
    lots = [df.iloc[i:i + 500] for i in range(0, len(df), 500)]
    _conn(tmp_path).load_batches(lots, table=str(cible), mode="replace")
    assert pq.ParquetFile(cible).metadata.num_row_groups == 6


def test_append_conserve_les_lignes_existantes(tmp_path: Path):
    cible = tmp_path / "out.parquet"
    df1, df2 = _donnees(800), _donnees(400)
    conn = _conn(tmp_path)
    conn.load_batches([df1], table=str(cible), mode="replace")
    conn.load_batches([df2], table=str(cible), mode="append")

    obtenu = pd.read_parquet(cible)
    attendu = pd.concat([df1, df2], ignore_index=True)
    pd.testing.assert_frame_equal(obtenu, attendu)


def test_append_sur_fichier_absent_cree_le_fichier(tmp_path: Path):
    cible = tmp_path / "sous" / "out.parquet"
    df = _donnees(100)
    _conn(tmp_path).load_batches([df], table=str(cible), mode="append")
    pd.testing.assert_frame_equal(pd.read_parquet(cible), df)


def test_append_refuse_un_schema_different(tmp_path: Path):
    cible = tmp_path / "out.parquet"
    conn = _conn(tmp_path)
    conn.load_batches([_donnees(50)], table=str(cible), mode="replace")
    avant = cible.read_bytes()

    with pytest.raises(ValueError, match="schema incompatible"):
        conn.load_batches([pd.DataFrame({"autre": [1, 2]})], table=str(cible), mode="append")

    assert cible.read_bytes() == avant, "le fichier d'origine doit rester intact"
    assert not list(cible.parent.glob("*.hydra-tmp")), "aucun fichier temporaire ne doit rester"


def test_lots_vides_ne_creent_rien(tmp_path: Path):
    cible = tmp_path / "out.parquet"
    _conn(tmp_path).load_batches([[], []], table=str(cible), mode="append")
    assert not cible.exists()


def test_replace_sans_donnees_efface_le_fichier(tmp_path: Path):
    cible = tmp_path / "out.parquet"
    conn = _conn(tmp_path)
    conn.load_batches([_donnees(10)], table=str(cible), mode="replace")
    assert cible.exists()
    conn.load_batches([], table=str(cible), mode="replace")
    assert not cible.exists()


def test_mode_invalide(tmp_path: Path):
    with pytest.raises(ValueError, match="mode"):
        _conn(tmp_path).load_batches([_donnees(5)], table=str(tmp_path / "o.parquet"), mode="upsert")


# --------------------------------------------------------- chaine de jobs

def _job(tmp_path: Path, nom: str, source: dict, destination: dict, steps: list) -> Path:
    job = tmp_path / nom
    job.mkdir(parents=True, exist_ok=True)
    (job / "sources.yaml").write_text(yaml.dump({"sources": {"s": source}}), encoding="utf-8")
    (job / "destinations.yaml").write_text(yaml.dump({"destinations": {"d": destination}}),
                                           encoding="utf-8")
    (job / "pipeline.yaml").write_text(yaml.dump({"pipeline": {"from": "s", "to": "d"}}),
                                       encoding="utf-8")
    (job / "transformations.yaml").write_text(yaml.dump({"transformations": {"steps": steps}}),
                                              encoding="utf-8")
    return job


def test_chaine_csv_parquet_csv(tmp_path: Path):
    src = tmp_path / "src.csv"
    _donnees(1500).to_csv(src, index=False)

    etapes = [{"cast": {"mapping": {"montant": "float"}}},
              {"filter": {"expr": "montant > 100"}},
              {"select": {"columns": ["id", "cat", "montant"]}}]

    # reference : CSV -> CSV
    ref = _job(tmp_path, "ref",
               {"type": "csv", "connection": {}, "extract": {"table": str(src), "batch_size": 400}},
               {"type": "csv", "connection": {},
                "load": {"table": str(tmp_path / "ref.csv"), "mode": "replace"}},
               etapes)
    r = JobExecutor(job_dir=ref).run()
    assert r.success, r.error

    # chaine : CSV -> Parquet, puis Parquet -> CSV
    j1 = _job(tmp_path, "j1",
              {"type": "csv", "connection": {}, "extract": {"table": str(src), "batch_size": 400}},
              {"type": "parquet", "connection": {},
               "load": {"table": str(tmp_path / "inter.parquet"), "mode": "replace"}},
              etapes)
    assert JobExecutor(job_dir=j1).run().success

    j2 = _job(tmp_path, "j2",
              {"type": "parquet", "connection": {},
               "extract": {"table": str(tmp_path / "inter.parquet"), "batch_size": 400}},
              {"type": "csv", "connection": {},
               "load": {"table": str(tmp_path / "final.csv"), "mode": "replace"}},
              [])
    assert JobExecutor(job_dir=j2).run().success

    attendu = pd.read_csv(tmp_path / "ref.csv")
    obtenu = pd.read_csv(tmp_path / "final.csv")
    pd.testing.assert_frame_equal(obtenu, attendu)


def test_le_parquet_intermediaire_conserve_les_types(tmp_path: Path):
    """L'interet du format : le job suivant n'a rien a recaster."""
    src = tmp_path / "src.csv"
    _donnees(300).to_csv(src, index=False)
    j = _job(tmp_path, "j",
             {"type": "csv", "connection": {}, "extract": {"table": str(src), "batch_size": 100}},
             {"type": "parquet", "connection": {},
              "load": {"table": str(tmp_path / "inter.parquet"), "mode": "replace"}},
             [{"cast": {"mapping": {"id": "int", "montant": "float"}}},
              {"select": {"columns": ["id", "montant", "cat"]}}])
    assert JobExecutor(job_dir=j).run().success

    relu = pd.read_parquet(tmp_path / "inter.parquet")
    assert str(relu["id"].dtype) in ("Int64", "int64")
    assert str(relu["montant"].dtype) == "float64"
