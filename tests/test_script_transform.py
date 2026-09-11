"""
Tests de la transformation 'script' (facon SSIS Script Component).

Couvre :
- Mode vectorized (Series)
- Mode row (ligne par ligne)
- Contrat inputs/outputs (validation)
- Sandbox securite (import / builtins interdits)
- Coercition des types de sortie
- Integration TransformParser -> PandasEngine
"""

import pandas as pd
import pytest

from hydra_etl.internal.engines.pandas_engine import PandasEngine
from hydra_etl.internal.parser.transform import TransformParser


@pytest.fixture
def engine():
    return PandasEngine()


@pytest.fixture
def df():
    return pd.DataFrame(
        {
            "price": [10.0, 20.0, 5.0],
            "quantity": [2, 3, 4],
            "currency": ["EUR", "USD", "EUR"],
        }
    )


# ---------------------------------------------------------------------
# Mode vectorized
# ---------------------------------------------------------------------

def test_script_vectorized_basic(engine, df):
    step = {
        "op": "script",
        "params": {
            "inputs": ["price", "quantity"],
            "outputs": {"total": "float"},
            "mode": "vectorized",
            "code": "total = price * quantity",
        },
    }
    out = engine.apply_step(df, step).output
    assert list(out["total"]) == [20.0, 60.0, 20.0]
    # les colonnes d'origine sont conservees
    assert "price" in out.columns and "currency" in out.columns


def test_script_vectorized_multi_output(engine, df):
    step = {
        "op": "script",
        "params": {
            "inputs": ["price", "quantity"],
            "outputs": {"total": "float", "double": "float"},
            "code": "total = price * quantity\ndouble = total * 2",
        },
    }
    out = engine.apply_step(df, step).output
    assert list(out["total"]) == [20.0, 60.0, 20.0]
    assert list(out["double"]) == [40.0, 120.0, 40.0]


def test_script_vectorized_uses_numpy(engine, df):
    import math as _m
    step = {
        "op": "script",
        "params": {
            "inputs": ["price"],
            "outputs": {"logp": "float"},
            "code": "logp = np.log(price)",
        },
    }
    out = engine.apply_step(df, step).output
    assert round(out["logp"].iloc[0], 4) == round(_m.log(10.0), 4)


# ---------------------------------------------------------------------
# Mode row
# ---------------------------------------------------------------------

def test_script_row_basic(engine, df):
    step = {
        "op": "script",
        "params": {
            "inputs": ["price", "quantity"],
            "outputs": {"total": "float", "label": "str"},
            "mode": "row",
            "code": "total = price * quantity\nlabel = 'big' if total > 30 else 'small'",
        },
    }
    out = engine.apply_step(df, step).output
    assert list(out["total"]) == [20.0, 60.0, 20.0]
    assert list(out["label"]) == ["small", "big", "small"]


# ---------------------------------------------------------------------
# Coercition des types de sortie
# ---------------------------------------------------------------------

def test_script_output_cast_int(engine, df):
    step = {
        "op": "script",
        "params": {
            "inputs": ["price", "quantity"],
            "outputs": {"total": "int"},
            "code": "total = price * quantity",
        },
    }
    out = engine.apply_step(df, step).output
    assert str(out["total"].dtype) == "Int64"


# ---------------------------------------------------------------------
# Contrat inputs / outputs
# ---------------------------------------------------------------------

def test_script_missing_input_column(engine, df):
    step = {
        "op": "script",
        "params": {
            "inputs": ["does_not_exist"],
            "outputs": {"x": "float"},
            "code": "x = does_not_exist * 2",
        },
    }
    with pytest.raises(ValueError, match="input inexistantes"):
        engine.apply_step(df, step)


def test_script_output_not_defined(engine, df):
    step = {
        "op": "script",
        "params": {
            "inputs": ["price"],
            "outputs": {"total": "float"},
            "code": "other = price * 2",  # 'total' jamais defini
        },
    }
    with pytest.raises(ValueError, match="non definie"):
        engine.apply_step(df, step)


# ---------------------------------------------------------------------
# Sandbox securite
# ---------------------------------------------------------------------

def test_script_import_forbidden(engine, df):
    step = {
        "op": "script",
        "params": {
            "inputs": ["price"],
            "outputs": {"x": "float"},
            "code": "import os\nx = price",
        },
    }
    with pytest.raises(ValueError, match="import.*interdit"):
        engine.apply_step(df, step)


def test_script_dunder_forbidden(engine, df):
    step = {
        "op": "script",
        "params": {
            "inputs": ["price"],
            "outputs": {"x": "float"},
            "code": "x = price.__class__",
        },
    }
    with pytest.raises(ValueError, match="interdit"):
        engine.apply_step(df, step)


def test_script_open_forbidden(engine, df):
    step = {
        "op": "script",
        "params": {
            "inputs": ["price"],
            "outputs": {"x": "float"},
            "code": "f = open('/etc/passwd')\nx = price",
        },
    }
    with pytest.raises(ValueError, match="interdit"):
        engine.apply_step(df, step)


# ---------------------------------------------------------------------
# Integration parser -> engine
# ---------------------------------------------------------------------

def test_script_via_parser(engine, df):
    raw = {
        "steps": [
            {
                "script": {
                    "inputs": ["price", "quantity"],
                    "outputs": {"total": "float"},
                    "mode": "vectorized",
                    "code": "total = price * quantity",
                }
            }
        ]
    }
    config = TransformParser().parse(raw)
    step = {"op": config.steps[0].op, "params": config.steps[0].params}
    out = engine.apply_step(df, step).output
    assert list(out["total"]) == [20.0, 60.0, 20.0]


def test_script_parser_rejects_bad_output_type():
    raw = {
        "steps": [
            {
                "script": {
                    "inputs": ["price"],
                    "outputs": {"total": "complex"},  # type non autorise
                    "code": "total = price",
                }
            }
        ]
    }
    with pytest.raises(Exception):
        TransformParser().parse(raw)
