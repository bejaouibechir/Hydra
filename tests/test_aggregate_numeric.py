"""aggregate : sum / mean sur une colonne texte.

pandas concatène les chaînes ("19.9" + "49.9" -> "19.949.9") au lieu de les
additionner. Une colonne lue d'un CSV sans `cast` est du texte : le total était
faux sans aucun message (0.19.0). Depuis 0.19.1, l'étape échoue et dit quoi faire.
"""
from __future__ import annotations

import pandas as pd
import pytest

from hydra_etl.internal.engines.pandas_engine import PandasEngine


def _agg(df, func, col="amount"):
    step = {"aggregate": {"by": ["day"], "agg": {"out": {"func": func, "col": col}}}}
    return PandasEngine().apply_step(df, step).output


TEXT = pd.DataFrame({"day": ["d1", "d1", "d2"], "amount": ["19.9", "49.9", "5"]})


@pytest.mark.parametrize("func", ["sum", "mean", "avg"])
def test_sum_or_mean_on_text_is_refused_with_the_fix(func):
    with pytest.raises(ValueError) as e:
        _agg(TEXT.copy(), func)
    msg = str(e.value)
    assert "needs a numeric column" in msg
    assert "'amount'" in msg
    assert "cast: {mapping: {amount: float}}" in msg


def test_after_cast_the_sum_is_numeric():
    df = TEXT.copy()
    df["amount"] = df["amount"].astype(float)
    out = _agg(df, "sum").sort_values("day").reset_index(drop=True)
    assert out["out"].tolist() == pytest.approx([69.8, 5.0])


@pytest.mark.parametrize("func", ["count", "min", "max", "first", "last"])
def test_other_functions_still_accept_text(func):
    out = _agg(TEXT.copy(), func)
    assert len(out) == 2


def test_integer_and_boolean_columns_are_numeric():
    df = pd.DataFrame({"day": ["d1", "d1"], "n": [1, 2], "ok": [True, False]})
    assert _agg(df, "sum", "n")["out"].tolist() == [3]
    assert _agg(df, "sum", "ok")["out"].tolist() == [1]


def test_text_column_with_only_nulls_is_not_refused():
    df = pd.DataFrame({"day": ["d1", "d1"], "amount": pd.Series([None, None], dtype=object)})
    out = _agg(df, "sum")
    assert len(out) == 1


def test_messages_are_in_english():
    df = TEXT.copy()
    with pytest.raises(ValueError, match="unknown source column 'nope'"):
        _agg(df, "count", "nope")
    with pytest.raises(ValueError, match="aggregate.by is required"):
        PandasEngine().apply_step(df, {"aggregate": {"by": [], "agg": {"x": "count"}}})


@pytest.mark.parametrize("engine", ["pandas", "duckdb"])
def test_job_on_csv_without_cast_fails_with_the_fix(tmp_path, monkeypatch, engine):
    """Un CSV relu sans cast : même message clair avec les deux moteurs
    (DuckDB rend la main à pandas au lieu de lever une Binder Error)."""
    if engine == "duckdb":
        pytest.importorskip("duckdb")
        pytest.importorskip("pyarrow")
    from hydra_etl.internal.runner.executor import JobExecutor
    monkeypatch.setenv("HYDRA_ENGINE", engine)
    job = tmp_path / "job"
    (job / "data").mkdir(parents=True)
    (job / "data" / "in.csv").write_text("day,amount\nd1,19.9\nd1,49.9\nd2,5\n", encoding="utf-8")
    (job / "sources.yaml").write_text(
        'sources:\n  src:\n    type: csv\n    extract:\n      table: data/in.csv\n', encoding="utf-8")
    (job / "destinations.yaml").write_text(
        'destinations:\n  dst:\n    type: csv\n    load:\n      table: data/out.csv\n      mode: replace\n',
        encoding="utf-8")
    (job / "pipeline.yaml").write_text("pipeline:\n  from: src\n  to: dst\n", encoding="utf-8")
    (job / "transformations.yaml").write_text(
        "steps:\n  - aggregate:\n      by: [day]\n      agg:\n        total: {func: sum, col: amount}\n",
        encoding="utf-8")
    res = JobExecutor(job_dir=str(job)).run()
    assert not res.success
    assert "sum needs a numeric column" in str(res.error)
    assert not (job / "data" / "out.csv").exists()
