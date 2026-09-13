"""
Parite numexpr / python pour filter et calculate.

Le garde-fou de expr_engine n'autorise numexpr que sur un sous-ensemble
d'expressions ; ce fichier verifie (a) que le garde-fou refuse bien tout
ce qui sort de ce sous-ensemble, (b) que sur ce sous-ensemble les deux
moteurs rendent exactement la meme chose, y compris avec des NaN, des
zeros au denominateur, des negatifs et de tres grandes valeurs.
"""

from __future__ import annotations

import random

import numpy as np
import pandas as pd
import pytest

from hydra_etl.internal.engines.expr_engine import choose_expr_engine, numexpr_mode
from hydra_etl.internal.engines.pandas_engine import PandasEngine

pytest.importorskip("numexpr")

N = 60_000  # au-dessus du seuil du garde-fou


def _frame(n: int = N, seed: int = 0) -> pd.DataFrame:
    rnd = np.random.default_rng(seed)
    a = rnd.normal(0, 100, n)
    a[rnd.integers(0, n, max(1, n // 500))] = np.nan
    b = rnd.normal(0, 1, n)
    b[rnd.integers(0, n, max(1, n // 500))] = 0.0  # divisions par zero
    return pd.DataFrame(
        {
            "a": a,
            "b": b,
            "c": rnd.integers(-1000, 1000, n),
            "d": rnd.integers(0, 5, n).astype(np.int32),
            "e": rnd.normal(0, 1e12, n),  # grandes valeurs
        }
    )


# ------------------------------------------------------------------ garde-fou

def _int_frame(n: int = N) -> pd.DataFrame:
    g = np.random.default_rng(11)
    return pd.DataFrame(
        {
            "i": g.integers(-10 ** 9, 10 ** 9, n),          # int64
            "j": g.integers(-10 ** 12, 10 ** 12, n),        # int64
            "k": g.integers(-5, 5, n).astype(np.int32),     # int32 : promu par numexpr
        }
    )


def test_mode_par_defaut_est_exact(monkeypatch):
    monkeypatch.delenv("HYDRA_NUMEXPR", raising=False)
    assert numexpr_mode() == "exact"


@pytest.mark.parametrize(
    "expr, attendu",
    [
        ("i * j + i - j * 2", "numexpr"),      # int64, + - * : exact
        ("(i + j) * (i - j) - j > 0", "numexpr"),
        ("i * j + i / 2 - j", "python"),       # division : non exacte
        ("i + j", "python"),                   # pas assez d'operations
        ("i * j + k - j", "python"),           # int32 : dtype promu
        ("i ** 2 + j * i - j", "python"),      # puissance
        ("i % 3 + j * i - j", "python"),       # modulo
        ("i // 3 + j * i - j", "python"),      # division entiere
        ("abs(i) + j * i - j", "python"),      # appel de fonction
        ("i * j + i - j and nom == 'x'", "python"),  # chaine
        ("i.sum() + j * i - j", "python"),     # attribut
        ("inconnue * j + i - j", "python"),    # colonne absente
    ],
)
def test_garde_fou_mode_exact(expr, attendu, monkeypatch):
    monkeypatch.delenv("HYDRA_NUMEXPR", raising=False)
    assert choose_expr_engine(_int_frame(), expr) == attendu


def test_mode_exact_refuse_les_flottants(monkeypatch):
    monkeypatch.delenv("HYDRA_NUMEXPR", raising=False)
    assert choose_expr_engine(_frame(N), "a * b + c * d - a / (b + 1)") == "python"


def test_mode_all_accepte_les_flottants(monkeypatch):
    monkeypatch.setenv("HYDRA_NUMEXPR", "all")
    assert choose_expr_engine(_frame(N), "a * b + c * d - a / (b + 1)") == "numexpr"
    assert choose_expr_engine(_frame(N), "a > 0.5") == "python"


def test_garde_fou_refuse_les_dtypes_extension(monkeypatch):
    monkeypatch.setenv("HYDRA_NUMEXPR", "all")
    df = _frame(N)
    df["c"] = pd.array(df["c"], dtype="Int64")
    assert choose_expr_engine(df, "a * b + c * d - a / (b + 1)") == "python"


def test_garde_fou_refuse_les_petits_volumes(monkeypatch):
    monkeypatch.delenv("HYDRA_NUMEXPR", raising=False)
    assert choose_expr_engine(_int_frame(1000), "i * j + i - j * 2") == "python"


def test_desactivation_par_variable_denvironnement(monkeypatch):
    monkeypatch.setenv("HYDRA_NUMEXPR", "0")
    assert choose_expr_engine(_int_frame(), "i * j + i - j * 2") == "python"


# --------------------------------------------------------------------- parite

_COLS = ["a", "b", "c", "d", "e"]
_OPS = ["+", "-", "*", "/"]


def _random_expr(rnd: random.Random, n_ops: int) -> str:
    expr = rnd.choice(_COLS)
    for _ in range(n_ops):
        op = rnd.choice(_OPS)
        rhs = rnd.choice(_COLS + ["2", "0.5", "-3", "10000"])
        if op == "/":
            rhs = f"({rhs} + 1)" if rnd.random() < 0.5 else rhs
        expr = f"({expr} {op} {rhs})" if rnd.random() < 0.4 else f"{expr} {op} {rhs}"
    return expr


def test_parite_exacte_sur_entiers():
    """Mode par defaut : int64 et + - * -> aucun ecart, valeur comme dtype."""
    rnd = random.Random(1234)
    g = np.random.default_rng(5)
    n = 5_000
    df = pd.DataFrame({
        "c": g.integers(-10 ** 9, 10 ** 9, n),
        "f": g.integers(-10 ** 15, 10 ** 15, n),
        "h": g.integers(-10 ** 18, 10 ** 18, n),
    })
    cols, ops = ["c", "f", "h"], ["+", "-", "*"]
    ecarts, testees = [], 0
    for _ in range(500):
        expr = rnd.choice(cols)
        for _ in range(rnd.randint(3, 6)):
            expr = f"{expr} {rnd.choice(ops)} {rnd.choice(cols + ['2', '7', '-3'])}"
        try:
            ref = df.eval(expr, engine="python")
            got = df.eval(expr, engine="numexpr")
        except Exception:
            continue
        testees += 1
        if not ref.equals(got):
            ecarts.append(expr)
        cond = f"({expr}) > 0"
        if not df.query(cond, engine="python").equals(df.query(cond, engine="numexpr")):
            ecarts.append(cond)
    assert testees > 100
    assert not ecarts, f"{len(ecarts)} ecart(s), ex. : {ecarts[:2]}"


def test_parite_approchee_sur_flottants():
    """Mode 'all' : sur les flottants, l'ecart reste au niveau du dernier bit.

    Ce test mesure l'ecart relatif maximal observe et le borne ; c'est la
    raison pour laquelle ce mode n'est pas le comportement par defaut.
    """
    rnd = random.Random(1234)
    df = _frame(5_000, seed=7)
    pire = 0.0
    pire_expr = ""
    testees = 0
    for _ in range(300):
        expr = _random_expr(rnd, rnd.randint(3, 6))
        try:
            ref = np.asarray(df.eval(expr, engine="python"), dtype="float64")
            got = np.asarray(df.eval(expr, engine="numexpr"), dtype="float64")
        except Exception:
            continue
        testees += 1
        fini = np.isfinite(ref) & np.isfinite(got)
        # meme motif de NaN / inf des deux cotes
        assert np.array_equal(np.isnan(ref), np.isnan(got)), expr
        assert np.array_equal(np.isinf(ref), np.isinf(got)), expr
        if fini.any():
            # ecart rapporte a l'ordre de grandeur de la colonne, et non a
            # chaque valeur : une soustraction de nombres proches amplifie
            # l'erreur relative ponctuelle sans que le calcul soit faux.
            echelle = max(float(np.max(np.abs(ref[fini]))), 1e-300)
            ecart = float(np.max(np.abs(ref[fini] - got[fini]))) / echelle
            if ecart > pire:
                pire, pire_expr = ecart, expr

    assert testees > 100
    # 2 ** -50 ~ 8,9e-16 : quelques ulp. Au-dela, ce ne serait plus de
    # l'arrondi mais un calcul different.
    assert pire <= 2 ** -50, f"ecart relatif max {pire:.3e} sur '{pire_expr}'"


def test_parite_filter_sur_flottants():
    rnd = random.Random(4321)
    df = _frame(5_000, seed=9)
    ecarts = []
    for _ in range(200):
        cond = f"({_random_expr(rnd, rnd.randint(3, 5))}) > 0"
        if rnd.random() < 0.4:
            cond += f" and ({_random_expr(rnd, 3)}) < 100"
        try:
            ref = df.query(cond, engine="python")
            got = df.query(cond, engine="numexpr")
        except Exception:
            continue
        if not ref.equals(got):
            ecarts.append(cond)
    assert not ecarts, f"{len(ecarts)} ecart(s), ex. : {ecarts[:2]}"


# ------------------------------------------------------- bout en bout (engine)

def test_calculate_donne_le_meme_resultat_avec_et_sans_numexpr(monkeypatch):
    df = _frame(N)
    step = {"calculate": {"column": "r", "expr": "a * b + c * d - a / (b + 1)"}}
    engine = PandasEngine()
    monkeypatch.setenv("HYDRA_NUMEXPR", "0")
    ref = engine.apply_step(df, step).output
    monkeypatch.setenv("HYDRA_NUMEXPR", "all")
    got = engine.apply_step(df, step).output
    pd.testing.assert_frame_equal(ref, got, check_exact=False, rtol=2 ** -50)


def test_filter_donne_le_meme_resultat_avec_et_sans_numexpr(monkeypatch):
    df = _frame(N)
    step = {"filter": {"expr": "(a * b + c * d - a / (b + 1)) > 0"}}
    engine = PandasEngine()
    monkeypatch.setenv("HYDRA_NUMEXPR", "0")
    ref = engine.apply_step(df, step).output
    monkeypatch.setenv("HYDRA_NUMEXPR", "all")
    got = engine.apply_step(df, step).output
    pd.testing.assert_frame_equal(ref, got)


def test_expression_invalide_garde_le_message_dorigine():
    df = _frame(N)
    engine = PandasEngine()
    with pytest.raises(ValueError, match="filter : expression invalide"):
        engine.apply_step(df, {"filter": {"expr": "a * b + c * d - zzz > 0"}})
    with pytest.raises(ValueError, match="calculate : expression invalide"):
        engine.apply_step(df, {"calculate": {"column": "r", "expr": "a * b + zzz - d"}})
