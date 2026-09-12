"""
Parité de l'opération `cast` après optimisation (module 4, volet Python).

Les chemins rapides (`astype` pour int/float, appel par valeur distincte pour
bool) doivent être indiscernables des implémentations d'origine, y compris
quand elles échouent : même valeur, même dtype, même type d'exception et même
message. Ce fichier garde une copie des implémentations de référence et compare.
"""
from __future__ import annotations

import random

import numpy as np
import pandas as pd
import pytest

from hydra_etl.internal.engines.pandas_engine import PandasEngine

ENGINE = PandasEngine.__new__(PandasEngine)   # _op_cast et ses aides sont sans état


# --- implémentations de référence (état du code avant optimisation) ----------

def ref_numeric(series: pd.Series, dtype: str) -> pd.Series:
    return pd.to_numeric(series, errors="raise").astype(dtype)


def ref_bool(series: pd.Series) -> pd.Series:
    TRUE_VALS = {"true", "1", "yes", "oui", "on"}
    FALSE_VALS = {"false", "0", "no", "non", "off"}

    def normalize(v):
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            if v == 1:
                return True
            if v == 0:
                return False
            raise ValueError(f"Valeur numerique {v} non convertible en bool (attendu 0 ou 1)")
        if isinstance(v, str):
            s = v.strip().lower()
            if s in TRUE_VALS:
                return True
            if s in FALSE_VALS:
                return False
            raise ValueError(f"String '{v}' non convertible en bool")
        raise ValueError(f"Type {type(v).__name__} non convertible en bool")

    return series.map(normalize)


def outcome(fn, *args):
    """Résultat de `fn`, ou son erreur, sous une forme comparable."""
    try:
        out = fn(*args)
    except Exception as exc:  # noqa: BLE001 - on compare aussi les échecs
        return ("error", type(exc).__name__, str(exc))
    # repr() plutôt que les valeurs : NaN n'est égal à rien, pas même à lui-même.
    return ("ok", str(out.dtype), repr(out.tolist()))


def compare(ref, new, *args):
    expected = outcome(ref, *args)
    got = outcome(new, *args)
    assert got == expected, f"\nréférence : {expected}\nobtenu    : {got}"


# --- cas ciblés -------------------------------------------------------------

INT_CASES = [
    ["1", "2", "3"], ["007", "-12", "+5"], [" 42 ", "7"], ["3.0", "4"], ["1e3"],
    ["1_000"], ["abc"], [""], ["nan"], ["inf"], ["0x10"], ["12,5"],
    ["99999999999999999999"], ["1", None], [1, 2], [1.0, 2.0], [1.5], [True, False],
    [], ["-0"], ["٣"],
]

FLOAT_CASES = INT_CASES + [
    [".5", "5."], ["1e400"], ["-inf", "nan"], ["1.7976931348623157e309"],
    ["0.1", "0.2"], [1.5, None],
]

BOOL_CASES = [
    ["true", "false"], ["TRUE", " yes ", "Non", "off"], ["oui", "1", "0"],
    ["true", "peut-être"], ["vrai"], [""], [0, 1], [0.0, 1.0], [2],
    [True, False], [None], [np.nan], [1, "true", True], [], ["1"] * 50 + ["x"],
    [{"a": 1}], [["x"]],
]

DTYPES = [None, "object", "string"]


def _series(values, dtype):
    if dtype == "string" and not all(isinstance(v, str) or v is None for v in values):
        pytest.skip("valeurs non textuelles")
    try:
        return pd.Series(values, dtype=dtype)
    except (TypeError, ValueError):
        pytest.skip("dtype impossible pour ces valeurs")


@pytest.mark.parametrize("dtype", DTYPES)
@pytest.mark.parametrize("values", INT_CASES, ids=repr)
def test_int_parity(values, dtype):
    s = _series(values, dtype)
    compare(lambda x: ref_numeric(x, "Int64"), lambda x: ENGINE._to_numeric_fast(x, "Int64"), s)


@pytest.mark.parametrize("dtype", DTYPES)
@pytest.mark.parametrize("values", FLOAT_CASES, ids=repr)
def test_float_parity(values, dtype):
    s = _series(values, dtype)
    compare(lambda x: ref_numeric(x, "float64"),
            lambda x: ENGINE._to_numeric_fast(x, "float64"), s)


@pytest.mark.parametrize("dtype", DTYPES)
@pytest.mark.parametrize("values", BOOL_CASES, ids=repr)
def test_bool_parity(values, dtype):
    s = _series(values, dtype)
    compare(ref_bool, ENGINE._cast_to_bool, s)


# --- tirage aléatoire -------------------------------------------------------

ALPHABET = "0123456789+-.eE_, \tabxinf"


@pytest.mark.parametrize("dtype", ["object", "string"])
def test_fuzz_numeric(dtype):
    rng = random.Random(20260912)
    for _ in range(1500):
        values = ["".join(rng.choice(ALPHABET) for _ in range(rng.randint(0, 6)))
                  for _ in range(rng.randint(1, 4))]
        s = pd.Series(values, dtype=dtype)
        compare(lambda x: ref_numeric(x, "Int64"),
                lambda x: ENGINE._to_numeric_fast(x, "Int64"), s)
        compare(lambda x: ref_numeric(x, "float64"),
                lambda x: ENGINE._to_numeric_fast(x, "float64"), s)


def test_fuzz_bool():
    rng = random.Random(20260913)
    pool = ["true", "false", "TRUE", " yes", "non ", "on", "off", "1", "0", "x", "",
            "oui", "OUI", "2", None, 0, 1, 2, True, False, 0.0, np.nan]
    for _ in range(1500):
        values = [rng.choice(pool) for _ in range(rng.randint(1, 6))]
        compare(ref_bool, ENGINE._cast_to_bool, pd.Series(values, dtype="object"))


# --- l'opération complète ---------------------------------------------------

def test_op_cast_end_to_end():
    df = pd.DataFrame({
        "i": ["1", "2", "3"], "f": ["1.5", "2.5", "3.5"], "s": [1, 2, 3],
        "b": ["true", "0", "oui"], "d": ["2026-01-01", "2026-02-01", "2026-03-01"],
    })
    out = ENGINE._op_cast(df, {"mapping": {
        "i": "int", "f": "float", "s": "str", "b": "bool", "d": "datetime"}})
    assert [str(out[c].dtype) for c in ("i", "f", "b")] == ["Int64", "float64", "bool"]
    assert out["b"].tolist() == [True, False, True]
    assert list(df.columns) == ["i", "f", "s", "b", "d"]      # entrée inchangée
    assert df["i"].tolist() == ["1", "2", "3"]


def test_op_cast_errors_keep_their_message():
    df = pd.DataFrame({"x": ["1", "deux"]})
    with pytest.raises(ValueError, match="cast : échec conversion colonne='x' vers type='int'"):
        ENGINE._op_cast(df, {"mapping": {"x": "int"}})
    with pytest.raises(ValueError, match="non convertible en bool"):
        ENGINE._op_cast(pd.DataFrame({"x": ["true", "zz"]}), {"mapping": {"x": "bool"}})
