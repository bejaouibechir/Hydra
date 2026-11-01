"""text_to_rows — une ligne par valeur d'une colonne texte."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from hydra_etl.internal.engines.pandas_engine import PandasEngine
from hydra_etl.internal.parser.transform import TransformParser
from hydra_etl.internal.runner.executor import JobExecutor
from hydra_etl.internal.runner.projection import required_columns


def _ttr(df, **p):
    return PandasEngine().apply_step(df, {"text_to_rows": p}).output


DF = pd.DataFrame({"id": [1, 2, 3, 4], "tags": ["a;b;c", "solo", None, " x ; ;y "]})


def test_split_and_copy_other_columns():
    out = _ttr(DF, column="tags", sep=";", index_column="pos")
    assert list(out.columns) == ["id", "tags", "pos"]
    assert out["id"].tolist() == [1, 1, 1, 2, 3, 4, 4]
    assert out["tags"].tolist() == ["a", "b", "c", "solo", None, "x", "y"]
    assert out["pos"].tolist() == [1, 2, 3, 1, pd.NA, 1, 2]


def test_separator_absent_gives_one_row():
    out = _ttr(pd.DataFrame({"t": ["abc"]}), column="t", sep="|")
    assert out["t"].tolist() == ["abc"]


def test_keep_empty_and_no_trim():
    out = _ttr(pd.DataFrame({"t": [" x ; ;y "]}), column="t", sep=";", trim=False, keep_empty=True)
    assert out["t"].tolist() == [" x ", " ", "y "]
    out = _ttr(pd.DataFrame({"t": ["a;;b"]}), column="t", sep=";", keep_empty=True)
    assert out["t"].tolist() == ["a", "", "b"]


def test_only_empty_values_keep_one_null_row():
    out = _ttr(pd.DataFrame({"id": [7], "t": [" ; ;"]}), column="t", sep=";", index_column="i")
    assert out["id"].tolist() == [7] and out["t"].isna().all() and out["i"].isna().all()


def test_regex_separator():
    out = _ttr(pd.DataFrame({"t": ["a, b;c|d"]}), column="t", sep=r"[,;|]", regex=True)
    assert out["t"].tolist() == ["a", "b", "c", "d"]


def test_non_text_values_are_split_as_text():
    out = _ttr(pd.DataFrame({"t": [123]}), column="t", sep="2")
    assert out["t"].tolist() == ["1", "3"]


def test_batches_give_the_same_result():
    eng, step = PandasEngine(), {"text_to_rows": {"column": "tags", "sep": ";", "index_column": "p"}}
    parts = [eng.apply_step(DF.iloc[i:i + 1].reset_index(drop=True), step).output for i in range(4)]
    pd.testing.assert_frame_equal(pd.concat(parts, ignore_index=True),
                                  _ttr(DF, column="tags", sep=";", index_column="p"))


def test_empty_frame():
    out = _ttr(DF.iloc[:0], column="tags", sep=";", index_column="p")
    assert len(out) == 0 and list(out.columns) == ["id", "tags", "p"]


@pytest.mark.parametrize("params, msg", [
    ({"column": "nope"}, "column 'nope' not found"),
    ({"column": "tags", "index_column": "id"}, "index_column 'id' already exists"),
])
def test_engine_errors(params, msg):
    with pytest.raises(ValueError, match=msg):
        _ttr(DF, **params)


@pytest.mark.parametrize("params, msg", [
    ({}, "column"),
    ({"column": "t", "sep": ""}, "sep cannot be empty"),
    ({"column": "t", "sep": "(", "regex": True}, "not a valid regular expression"),
    ({"column": "t", "index_column": "t"}, "must differ from column"),
    ({"column": "t", "separator": ";"}, "separator"),
])
def test_parser_errors(params, msg):
    with pytest.raises(Exception, match=msg):
        TransformParser().parse({"steps": [{"text_to_rows": params}]})


def test_parser_ok():
    TransformParser().parse({"steps": [{"text_to_rows": {"column": "t", "sep": ";", "index_column": "p"}}]})


def test_projection_reads_the_split_column():
    steps = [{"text_to_rows": {"column": "tags", "sep": ";", "index_column": "p"}},
             {"select": {"columns": ["id", "tags", "p"]}}]
    assert required_columns(steps) == {"id", "tags"}


def _job(tmp: Path, steps: str) -> Path:
    job = tmp / "job"
    (job / "data").mkdir(parents=True)
    rows = "".join(f'{i},"{";".join(f"t{k}" for k in range(i % 4))}"\n' for i in range(300))
    (job / "data" / "in.csv").write_text("id,tags\n" + rows, encoding="utf-8")
    (job / "sources.yaml").write_text(
        "sources:\n  src:\n    type: csv\n    extract:\n      table: data/in.csv\n      batch_size: 100\n",
        encoding="utf-8")
    (job / "destinations.yaml").write_text(
        "destinations:\n  dst:\n    type: csv\n    load:\n      table: data/out.csv\n      mode: replace\n",
        encoding="utf-8")
    (job / "pipeline.yaml").write_text("pipeline:\n  from: src\n  to: dst\n", encoding="utf-8")
    (job / "transformations.yaml").write_text("steps:\n" + steps, encoding="utf-8")
    return job


@pytest.mark.parametrize("engine", ["pandas", "duckdb"])
def test_job_then_aggregate_same_result(tmp_path, monkeypatch, engine):
    if engine == "duckdb":
        pytest.importorskip("duckdb")
        pytest.importorskip("pyarrow")
    monkeypatch.setenv("HYDRA_ENGINE", engine)
    job = _job(tmp_path, "  - text_to_rows: {column: tags, sep: ';', index_column: pos}\n"
                         "  - aggregate:\n      by: [tags]\n      agg:\n        n: {func: count, col: id}\n")
    r = JobExecutor(job_dir=str(job)).run()
    assert r.success, r.error
    out = pd.read_csv(job / "data" / "out.csv")
    assert out.to_dict("list") == {"tags": ["t0", "t1", "t2"], "n": [225, 150, 75]}
