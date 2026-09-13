"""
Projection statique : ne lire que les colonnes dont le job se sert.

Deux garanties a tenir :
1. l'analyse rend None (= tout lire) des qu'il y a le moindre doute ;
2. avec ou sans projection, la sortie du job est identique octet pour octet.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd
import pytest
import yaml

from hydra_etl.internal.runner.executor import JobExecutor
from hydra_etl.internal.runner.projection import required_columns


# --------------------------------------------------------------- analyse seule

def _cols(steps) -> Optional[set]:
    return required_columns(steps)


def test_selection_finale_donne_les_colonnes_source():
    steps = [
        {"cast": {"mapping": {"order_id": "int", "unit_price": "float"}}},
        {"filter": {"expr": "status == 'completed'"}},
        {"calculate": {"column": "revenue", "expr": "unit_price * qty"}},
        {"rename": {"mapping": {"customer_id": "client_id"}}},
        {"select": {"columns": ["order_id", "client_id", "revenue"]}},
        {"sort": {"by": ["revenue"], "ascending": False}},
    ]
    assert _cols(steps) == {
        "order_id", "customer_id", "unit_price", "qty", "status",
    }


def test_aggregate_final_donne_les_colonnes_source():
    steps = [
        {"cast": {"mapping": {"unit_price": "float", "qty": "int"}}},
        {"calculate": {"column": "revenue", "expr": "unit_price * qty"}},
        {"aggregate": {"by": ["category"],
                       "agg": {"t": {"func": "sum", "col": "revenue"},
                               "n": {"func": "count", "col": "order_id"}}}},
    ]
    assert _cols(steps) == {"category", "unit_price", "qty", "order_id"}


def test_rename_est_inverse():
    steps = [
        {"rename": {"mapping": {"a": "x", "b": "y"}}},
        {"select": {"columns": ["x", "c"]}},
    ]
    assert _cols(steps) == {"a", "c"}


def test_calculate_remplacant_une_colonne_source():
    steps = [
        {"calculate": {"column": "prix", "expr": "prix_ht * 1.2"}},
        {"select": {"columns": ["id", "prix"]}},
    ]
    assert _cols(steps) == {"id", "prix_ht"}


@pytest.mark.parametrize(
    "steps, raison",
    [
        ([{"filter": {"expr": "a > 1"}}], "rien ne fixe les colonnes"),
        ([{"script": {"code": "x = 1"}}, {"select": {"columns": ["a"]}}], "script opaque"),
        ([{"join": {"right": "s2", "on": ["id"]}}, {"select": {"columns": ["a"]}}], "join opaque"),
        ([{"deduplicate": {}}, {"select": {"columns": ["a"]}}], "dedup sur toutes les colonnes"),
        ([{"pivot": {}}, {"select": {"columns": ["a"]}}], "pivot opaque"),
        ([{"filter": {"expr": "montant > @seuil"}}, {"select": {"columns": ["a"]}}], "expression non analysable"),
        ([{"filter": {"expr": "abs(a) > 1"}}, {"select": {"columns": ["a"]}}], "appel de fonction"),
        ([{"rename": {"mapping": {"a": "z", "b": "z"}}}, {"select": {"columns": ["z"]}}], "rename ambigu"),
        ([{"inconnue": {}}, {"select": {"columns": ["a"]}}], "operation inconnue"),
        ([], "pipeline vide"),
    ],
)
def test_prudence_rend_tout_lire(steps, raison):
    assert _cols(steps) is None, raison


def test_desactivation_par_variable_denvironnement(monkeypatch):
    monkeypatch.setenv("HYDRA_PROJECTION", "0")
    assert _cols([{"select": {"columns": ["a"]}}]) is None


# ------------------------------------------------------------- bout en bout

_LIGNES = 300
_COLONNES = ["order_id", "customer_id", "product", "categorie",
             "prix", "qty", "statut", "note_libre"]


def _job(tmp_path: Path, steps: list, nom: str = "job") -> Path:
    job = tmp_path / nom
    job.mkdir()
    src = job / "in.csv"
    pd.DataFrame({
        "order_id": range(1, _LIGNES + 1),
        "customer_id": [i % 37 for i in range(_LIGNES)],
        "product": [f"p{i % 11}" for i in range(_LIGNES)],
        "categorie": [["a", "b", "c"][i % 3] for i in range(_LIGNES)],
        "prix": [round(1 + i % 97 + i / 1000, 2) for i in range(_LIGNES)],
        "qty": [1 + i % 7 for i in range(_LIGNES)],
        "statut": [["completed", "pending"][i % 2] for i in range(_LIGNES)],
        "note_libre": [f"commentaire tres long numero {i}" for i in range(_LIGNES)],
    }).to_csv(src, index=False)

    (job / "sources.yaml").write_text(yaml.dump({
        "sources": {"s": {"type": "csv", "connection": {},
                          "extract": {"table": str(src), "batch_size": 100}}}}), encoding="utf-8")
    (job / "destinations.yaml").write_text(yaml.dump({
        "destinations": {"d": {"type": "csv", "connection": {},
                               "load": {"table": str(job / "out.csv"), "mode": "replace"}}}}),
        encoding="utf-8")
    (job / "pipeline.yaml").write_text(yaml.dump({"pipeline": {"from": "s", "to": "d"}}),
                                       encoding="utf-8")
    (job / "transformations.yaml").write_text(yaml.dump({"transformations": {"steps": steps}}),
                                              encoding="utf-8")
    return job


_PIPELINES = {
    "select_final": [
        {"cast": {"mapping": {"prix": "float", "qty": "int"}}},
        {"filter": {"expr": "statut == 'completed'"}},
        {"calculate": {"column": "revenu", "expr": "prix * qty"}},
        {"rename": {"mapping": {"customer_id": "client"}}},
        {"select": {"columns": ["order_id", "client", "revenu"]}},
        {"sort": {"by": ["revenu"], "ascending": False}},
    ],
    "aggregate_final": [
        {"cast": {"mapping": {"prix": "float", "qty": "int"}}},
        {"calculate": {"column": "revenu", "expr": "prix * qty"}},
        {"aggregate": {"by": ["categorie"],
                       "agg": {"total": {"func": "sum", "col": "revenu"},
                               "n": {"func": "count", "col": "order_id"}}}},
    ],
    "dedup_liste": [
        {"deduplicate": {"columns": ["categorie", "product"]}},
        {"select": {"columns": ["categorie", "product"]}},
    ],
    "sans_projection_possible": [
        {"cast": {"mapping": {"prix": "float"}}},
        {"filter": {"expr": "prix > 10"}},
    ],
}


@pytest.mark.parametrize("nom", sorted(_PIPELINES))
def test_sortie_identique_avec_et_sans_projection(tmp_path: Path, nom, monkeypatch):
    steps = _PIPELINES[nom]

    monkeypatch.setenv("HYDRA_PROJECTION", "0")
    job_ref = _job(tmp_path, steps, nom + "_ref")
    res_ref = JobExecutor(job_dir=job_ref).run()
    assert res_ref.success, res_ref.error
    attendu = (job_ref / "out.csv").read_bytes()

    monkeypatch.setenv("HYDRA_PROJECTION", "1")
    job_new = _job(tmp_path, steps, nom + "_new")
    res_new = JobExecutor(job_dir=job_new).run()
    assert res_new.success, res_new.error

    assert (job_new / "out.csv").read_bytes() == attendu
    assert res_new.rows_in == res_ref.rows_in
    assert res_new.rows_out == res_ref.rows_out


def test_colonne_absente_garde_le_message_dorigine(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HYDRA_PROJECTION", "1")
    job = _job(tmp_path, [{"select": {"columns": ["order_id", "colonne_absente"]}}])
    res = JobExecutor(job_dir=job).run()
    assert res.success is False
    assert "colonnes inexistantes" in (res.error or "")


def test_connecteur_csv_projette_reellement(tmp_path: Path):
    from hydra_etl.internal.connector.csv_connector import CSVConnector

    src = tmp_path / "in.csv"
    pd.DataFrame({"a": [1, 2], "b": [3, 4], "c": [5, 6]}).to_csv(src, index=False)
    conn = CSVConnector(name="s", config={"type": "csv"}, job_dir=str(tmp_path))
    conn.set_projection(["a", "c"])
    frames = list(conn.extract_frames(table=str(src), batch_size=10))
    assert [list(f.columns) for f in frames] == [["a", "c"]]

    # projection citant une colonne absente : on ne lit que ce qui existe
    conn.set_projection(["a", "zzz"])
    frames = list(conn.extract_frames(table=str(src), batch_size=10))
    assert [list(f.columns) for f in frames] == [["a"]]

    # projection None : tout, comme avant
    conn.set_projection(None)
    frames = list(conn.extract_frames(table=str(src), batch_size=10))
    assert [list(f.columns) for f in frames] == [["a", "b", "c"]]
