"""join how: cross — produit cartésien, sans clé, garde-fou max_rows."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from hydra_etl.internal.engines.pandas_engine import PandasEngine
from hydra_etl.internal.parser.transform import TransformParser
from hydra_etl.internal.runner.executor import JobExecutor

LEFT = pd.DataFrame({"id": [1, 2, 3], "v": ["a", "b", "c"]})
RIGHT = [{"day": "mon", "v": 10}, {"day": "tue", "v": 20}]


def _cross(df, rows, **kw):
    return PandasEngine().apply_step(df, {"join": {"how": "cross", "_right_rows": rows, **kw}}).output


def test_cartesian_product_order_and_suffix():
    out = _cross(LEFT, RIGHT)
    assert list(out.columns) == ["id", "v", "day", "v_r"]
    assert out[["id", "day"]].values.tolist() == [
        [1, "mon"], [1, "tue"], [2, "mon"], [2, "tue"], [3, "mon"], [3, "tue"]]


def test_empty_sides():
    assert len(_cross(LEFT.iloc[:0], RIGHT)) == 0
    out = _cross(LEFT, [])
    assert len(out) == 0 and list(out.columns) == ["id", "v"]


def test_batches_give_the_same_result_as_one_pass():
    eng, step = PandasEngine(), {"join": {"how": "cross", "_right_rows": RIGHT}}
    parts = [eng.apply_step(LEFT.iloc[i:i + 1].reset_index(drop=True), step).output for i in range(3)]
    pd.testing.assert_frame_equal(pd.concat(parts, ignore_index=True), _cross(LEFT, RIGHT))


def test_max_rows_is_cumulative_over_batches():
    eng = PandasEngine()
    step = {"join": {"how": "cross", "_right_rows": RIGHT, "max_rows": 5}}
    eng.apply_step(LEFT.iloc[:2], step)                       # 4 lignes
    with pytest.raises(ValueError, match=r"6 rows would be produced, more than max_rows \(5\)"):
        eng.apply_step(LEFT.iloc[2:], step)                   # 4 + 2 > 5


def test_default_limit(monkeypatch):
    monkeypatch.setattr(PandasEngine, "CROSS_MAX_ROWS", 3)
    with pytest.raises(ValueError, match="max_rows"):
        _cross(LEFT, RIGHT)


@pytest.mark.parametrize("extra, msg", [
    ({"key": "id"}, "how: cross takes no key — remove key"),
    ({"left_key": "id", "right_key": "id"}, "remove left_key, right_key"),
])
def test_keys_are_refused(extra, msg):
    with pytest.raises(Exception, match=msg):
        TransformParser().parse({"steps": [{"join": {"right": "cal", "how": "cross", **extra}}]})
    with pytest.raises(ValueError, match=msg):
        _cross(LEFT, RIGHT, **extra)


@pytest.mark.parametrize("params, msg", [
    ({"how": "cross", "max_rows": 0}, "positive integer"),
    ({"how": "inner", "key": "id", "max_rows": 10}, "only applies to how: cross"),
])
def test_max_rows_validation(params, msg):
    with pytest.raises(Exception, match=msg):
        TransformParser().parse({"steps": [{"join": {"right": "cal", **params}}]})


def test_parser_accepts_cross_without_key():
    TransformParser().parse({"steps": [{"join": {"right": "cal", "how": "cross", "max_rows": 100}}]})


def _job(tmp: Path, steps: str) -> Path:
    job = tmp / "job"
    (job / "data").mkdir(parents=True)
    (job / "data" / "in.csv").write_text(
        "id,amount\n" + "".join(f"{i},{i * 10}\n" for i in range(250)), encoding="utf-8")
    (job / "data" / "cal.csv").write_text("month\n01\n02\n03\n", encoding="utf-8")
    (job / "sources.yaml").write_text(
        "sources:\n  src:\n    type: csv\n    extract:\n      table: data/in.csv\n      batch_size: 100\n"
        "  cal:\n    type: csv\n    extract:\n      table: data/cal.csv\n", encoding="utf-8")
    (job / "destinations.yaml").write_text(
        "destinations:\n  dst:\n    type: csv\n    load:\n      table: data/out.csv\n      mode: replace\n",
        encoding="utf-8")
    (job / "pipeline.yaml").write_text("pipeline:\n  from: src\n  to: dst\n", encoding="utf-8")
    (job / "transformations.yaml").write_text("steps:\n" + steps, encoding="utf-8")
    return job


def test_job_cross_join(tmp_path):
    job = _job(tmp_path, "  - join: {right: cal, how: cross}\n")
    r = JobExecutor(job_dir=str(job)).run()
    assert r.success, r.error
    out = pd.read_csv(job / "data" / "out.csv", dtype=str)
    assert len(out) == 750 and list(out.columns) == ["id", "amount", "month"]
    assert out["month"].tolist()[:6] == ["01", "02", "03"] * 2


def test_job_cross_join_max_rows_stops_the_run(tmp_path):
    job = _job(tmp_path, "  - join: {right: cal, how: cross, max_rows: 500}\n")
    r = JobExecutor(job_dir=str(job)).run()
    assert not r.success and "max_rows (500)" in r.error


@pytest.mark.parametrize("engine", ["pandas", "duckdb"])
def test_cross_join_then_aggregate_same_result(tmp_path, monkeypatch, engine):
    if engine == "duckdb":
        pytest.importorskip("duckdb")
        pytest.importorskip("pyarrow")
    monkeypatch.setenv("HYDRA_ENGINE", engine)
    job = _job(tmp_path, "  - join: {right: cal, how: cross}\n"
                         "  - cast: {mapping: {amount: float}}\n"
                         "  - aggregate:\n      by: [month]\n      agg:\n"
                         "        total: {func: sum, col: amount}\n        n: {func: count, col: id}\n")
    r = JobExecutor(job_dir=str(job)).run()
    assert r.success, r.error
    out = pd.read_csv(job / "data" / "out.csv", dtype={"month": str})
    assert out.to_dict("list") == {"month": ["01", "02", "03"], "total": [311250.0] * 3, "n": [250] * 3}
