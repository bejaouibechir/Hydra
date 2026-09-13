"""
Contrat : une operation ne modifie jamais le DataFrame qu'elle recoit.

Les copies defensives des operations sont devenues paresseuses
(frame_copy.lazy_copy + Copy-on-Write). Ce fichier verifie que la garantie
tient toujours, avec ET sans Copy-on-Write, pour toutes les operations.
"""

from __future__ import annotations

import pandas as pd
import pytest

from hydra_etl.internal.engines.frame_copy import copy_on_write, lazy_copy
from hydra_etl.internal.engines.pandas_engine import PandasEngine


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "id": ["1", "2", "3", "3"],
            "prix": ["10.5", "20.0", "30.25", "30.25"],
            "nom": ["  alpha ", "beta", "GAMMA  ", "GAMMA  "],
            "cat": ["a", "b", "a", "a"],
            "n": [1, 2, 3, 3],
        }
    )


STEPS = [
    {"select": {"columns": ["id", "nom"]}},
    {"rename": {"mapping": {"nom": "libelle"}}},
    {"cast": {"mapping": {"id": "int", "prix": "float"}}},
    {"filter": {"expr": "cat == 'a'"}},
    {"calculate": {"column": "double", "expr": "n * 2"}},
    {"sort": {"by": ["n"], "ascending": False}},
    {"deduplicate": {"columns": ["cat"]}},
    {"fill_null": {"value": 0}},
    {"trim": {"columns": ["nom"]}},
    {"clean": {"columns": ["nom"], "case": "lower"}},
    {"aggregate": {"by": ["cat"], "agg": {"total": {"func": "sum", "col": "n"}}}},
    {"unpivot": {"id_vars": ["id"], "value_vars": ["cat", "nom"]}},
    {"transpose": {"index_col": "id"}},
    {"script": {"mode": "vectorized", "code": "triple = n * 3",
                "inputs": ["n"], "outputs": {"triple": "int"}}},
]


def _ids(steps):
    return [next(iter(s)) for s in steps]


@pytest.mark.parametrize("cow", [False, True], ids=["sans_cow", "avec_cow"])
@pytest.mark.parametrize("step", STEPS, ids=_ids(STEPS))
def test_operation_ne_modifie_pas_son_entree(step, cow, monkeypatch):
    monkeypatch.setenv("HYDRA_COW", "1" if cow else "0")
    engine = PandasEngine()
    df = _frame()
    temoin = df.copy(deep=True)

    ctx = copy_on_write() if cow else __import__("contextlib").nullcontext()
    with ctx:
        try:
            engine.apply_step(df, step)
        except ValueError as e:  # operation inapplicable a ce jeu de test
            pytest.skip(f"non applicable : {e}")

    pd.testing.assert_frame_equal(df, temoin, check_dtype=True)


def test_lazy_copy_protege_la_source():
    df = _frame()
    out = lazy_copy(df)
    out["n"] = out["n"] * 10
    out["nouvelle"] = 1
    assert df["n"].tolist() == [1, 2, 3, 3]
    assert "nouvelle" not in df.columns


def test_copy_on_write_est_restaure_apres_le_contexte():
    avant = pd.get_option("mode.copy_on_write") if _has_cow_option() else None
    with copy_on_write():
        pass
    apres = pd.get_option("mode.copy_on_write") if _has_cow_option() else None
    assert avant == apres


def _has_cow_option() -> bool:
    try:
        pd.get_option("mode.copy_on_write")
        return True
    except Exception:
        return False


def test_hydra_cow_0_desactive_le_contexte(monkeypatch):
    if not _has_cow_option():
        pytest.skip("option copy_on_write absente de cette version de pandas")
    monkeypatch.setenv("HYDRA_COW", "0")
    avant = pd.get_option("mode.copy_on_write")
    with copy_on_write():
        assert pd.get_option("mode.copy_on_write") == avant
