"""window — rang (row_number, rank, dense_rank) et décalage (lag, lead) ;
mêmes résultats en pandas et en DuckDB."""
from __future__ import annotations

import random
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from hydra_etl.internal.engines.pandas_engine import PandasEngine
from hydra_etl.internal.parser.transform import TransformParser
from hydra_etl.internal.runner.executor import JobExecutor
from hydra_etl.internal.runner.projection import required_columns


def _w(df, **p):
    return PandasEngine().apply_step(df, {"window": p}).output


DF = pd.DataFrame({
    "cust": ["A", "B", "A", "A", "B", "A"],
    "day": [3, 1, 1, 3, 2, None],
    "amount": [30, 5, 10, 31, 7, 99],
})


def test_rank_functions():
    out = _w(DF, partition_by="cust", order_by=["day"],
             columns={"rn": {"func": "row_number"}, "rk": {"func": "rank"}, "dr": {"func": "dense_rank"}})
    assert list(out.columns) == ["cust", "day", "amount", "rn", "rk", "dr"]
    # lignes dans l'ordre d'entrée ; A : day 1, 3, 3 (égalité : ordre d'entrée), null en dernier
    assert out["rn"].tolist() == [2, 1, 1, 3, 2, 4]
    assert out["rk"].tolist() == [2, 1, 1, 2, 2, 4]
    assert out["dr"].tolist() == [2, 1, 1, 2, 2, 3]
    assert str(out["rn"].dtype) == "int64"


def test_desc_keeps_nulls_last():
    out = _w(DF, partition_by=["cust"], order_by=[{"col": "day", "desc": True}],
             columns={"rn": {"func": "row_number"}})
    assert out["rn"].tolist() == [1, 2, 3, 2, 1, 4]


def test_lag_lead():
    out = _w(DF, partition_by="cust", order_by=["day"], columns={
        "prev": {"func": "lag", "col": "amount"},
        "prev0": {"func": "lag", "col": "amount", "default": 0},
        "next2": {"func": "lead", "col": "amount", "offset": 2}})
    # A trié : 10 (day1), 30 (day3), 31 (day3), 99 (null) ; B : 5, 7
    assert out["prev0"].tolist() == [10, 0, 0, 30, 5, 31]
    assert str(out["prev0"].dtype) == "int64"
    assert out["prev"].isna().tolist() == [False, True, True, False, False, False]
    assert out["next2"].tolist()[2] == 31 and out["next2"].isna().sum() == 4


def test_no_partition_is_the_whole_table():
    out = _w(DF, order_by=["amount"], columns={"rn": {"func": "row_number"}})
    assert out["rn"].tolist() == [4, 1, 3, 5, 2, 6]


def test_null_partition_is_its_own_group():
    df = pd.DataFrame({"p": ["x", None, None], "o": [1, 2, 1]})
    assert _w(df, partition_by="p", order_by="o", columns={"r": {"func": "row_number"}})["r"].tolist() == [1, 2, 1]


def test_empty_frame():
    out = _w(DF.iloc[:0], order_by="day", columns={"r": {"func": "rank"}, "l": {"func": "lag", "col": "amount"}})
    assert len(out) == 0 and list(out.columns)[-2:] == ["r", "l"]


@pytest.mark.parametrize("params, msg", [
    ({"order_by": "day", "columns": {"r": {"func": "ntile"}}}, "function 'ntile' is not supported"),
    ({"columns": {"r": {"func": "row_number"}}}, "row_number needs window.order_by"),
    ({"order_by": "day", "columns": {"r": {"func": "lag"}}}, "lag needs col"),
    ({"order_by": "day", "columns": {"r": {"func": "lag", "col": "a", "offset": 0}}}, "offset must be an integer >= 1"),
    ({"order_by": "day", "columns": {"r": {"func": "rank", "col": "a"}}}, "col not allowed with rank"),
    ({"order_by": "day", "columns": {}}, "at least one output column"),
    ({"columns": {"r": {"func": "cumsum", "col": "x"}}}, "cumsum needs window.order_by"),
    ({"columns": {"r": {"func": "sum"}}}, "sum needs col"),
    ({"columns": {"r": {"func": "max", "col": "x", "offset": 2}}}, "offset not allowed with max"),
    ({"order_by": "day", "columns": {"r": {"func": "rank"}}, "partiton_by": "x"}, "unknown option"),
    ({"order_by": [{"col": "day", "desc": "yes"}], "columns": {"r": {"func": "rank"}}}, "desc must be true or false"),
])
def test_validation(params, msg):
    with pytest.raises(Exception, match=msg):
        TransformParser().parse({"steps": [{"window": params}]})


CUM = pd.DataFrame({"p": ["a", "a", "a", "b", "a"], "o": [1, 2, 3, 1, 4],
                    "x": [5.0, np.nan, 2.0, 7.0, 9.0], "i": [1, 2, 3, 4, 5], "s": [None, "k", "j", "z", None]})


def test_cumulative_functions():
    out = _w(CUM, partition_by="p", order_by="o", columns={
        "cs": {"func": "cumsum", "col": "x"}, "ci": {"func": "cumsum", "col": "i"},
        "cn": {"func": "cumcount", "col": "x"}, "cr": {"func": "cumcount"},
        "mn": {"func": "cummin", "col": "x"}, "mx": {"func": "cummax", "col": "x"}})
    assert out["cs"].tolist() == [5.0, 5.0, 7.0, 7.0, 16.0]       # valeur nulle : cumul gardé
    assert out["ci"].tolist() == [1, 3, 6, 4, 11] and str(out["ci"].dtype) == "int64"
    assert out["cn"].tolist() == [1, 1, 2, 1, 3] and out["cr"].tolist() == [1, 2, 3, 1, 4]
    assert out["mn"].tolist() == [5.0, 5.0, 2.0, 7.0, 2.0] and out["mx"].tolist() == [5.0, 5.0, 5.0, 7.0, 9.0]


def test_partition_aggregates():
    out = _w(CUM, partition_by="p", order_by=[{"col": "o", "desc": True}], columns={
        "t": {"func": "sum", "col": "x"}, "m": {"func": "mean", "col": "i"}, "n": {"func": "count", "col": "x"},
        "lo": {"func": "min", "col": "s"}, "f": {"func": "first", "col": "s"}, "l": {"func": "last", "col": "s"}})
    assert out["t"].tolist() == [16.0, 16.0, 16.0, 7.0, 16.0]
    assert out["m"].tolist() == [2.75, 2.75, 2.75, 4.0, 2.75]
    assert out["n"].tolist() == [3, 3, 3, 1, 3]
    assert out["lo"].tolist() == ["j", "j", "j", "z", "j"]
    # ordre o desc : a = o4 (None), o3 j, o2 k, o1 (None) -> premier non nul j, dernier k
    assert out["f"].tolist() == ["j", "j", "j", "z", "j"] and out["l"].tolist() == ["k", "k", "k", "z", "k"]


def test_partition_aggregates_need_no_order():
    out = _w(CUM, partition_by="p", columns={"t": {"func": "sum", "col": "i"}, "f": {"func": "first", "col": "s"}})
    assert out["t"].tolist() == [11, 11, 11, 4, 11] and out["f"].tolist() == ["k", "k", "k", "z", "k"]


def test_sum_of_empty_partition_is_zero():
    df = pd.DataFrame({"p": ["a", "b"], "x": [np.nan, 1.0]})
    assert _w(df, partition_by="p", columns={"t": {"func": "sum", "col": "x"}})["t"].tolist() == [0.0, 1.0]


@pytest.mark.parametrize("params, msg", [
    ({"order_by": "nope", "columns": {"r": {"func": "rank"}}}, "column\\(s\\) not found: nope"),
    ({"order_by": "o", "columns": {"r": {"func": "cumsum", "col": "s"}}}, "cumsum needs a numeric column"),
    ({"columns": {"r": {"func": "mean", "col": "s"}}}, "mean needs a numeric column"),
    ({"order_by": "day", "columns": {"amount": {"func": "rank"}}}, "already exist: amount"),
])
def test_engine_errors(params, msg):
    with pytest.raises(ValueError, match=msg):
        _w(CUM if "o" in str(params.get("order_by")) or "mean" in str(params) else DF, **params)


def test_projection():
    steps = [{"window": {"partition_by": "cust", "order_by": "day",
                         "columns": {"r": {"func": "lag", "col": "amount"}}}},
             {"select": {"columns": ["cust", "r"]}}]
    assert required_columns(steps) == {"cust", "day", "amount"}


# ── Parité pandas / DuckDB ──────────────────────────────────────────────────
def _random_case(rnd):
    n = rnd.randint(1, 60)
    df = pd.DataFrame({
        "p": [rnd.choice(["a", "b", "c", None]) for _ in range(n)],
        "q": [rnd.randint(0, 2) for _ in range(n)],
        "o": [rnd.choice([1.5, 2.0, 3.0, np.nan]) for _ in range(n)],
        "s": [rnd.choice(["x", "y", "z", None]) for _ in range(n)],
        "v": [rnd.randint(-5, 5) for _ in range(n)],
        "w": pd.array([rnd.randint(0, 9) for _ in range(n)], dtype="Int64"),   # cast: int
    })
    df.loc[0, ["p", "s"]] = ["a", "x"]   # colonne entièrement vide : typée par DuckDB, hors sujet ici
    part = rnd.choice([None, "p", ["p", "q"], "q"])
    order = rnd.choice([["o"], [{"col": "o", "desc": True}], ["s", {"col": "v", "desc": True}], ["q", "o"]])
    cols = {}
    for k in range(rnd.randint(1, 4)):
        f = rnd.choice(["row_number", "rank", "dense_rank", "lag", "lead", "cumsum", "cumcount",
                        "cummin", "cummax", "sum", "mean", "min", "max", "count", "first", "last"])
        spec = {"func": f}
        if f in ("cumsum", "cummin", "cummax", "sum", "mean"):
            spec["col"] = rnd.choice(["v", "o", "w"])
        elif f in ("min", "max", "count", "first", "last") or (f == "cumcount" and rnd.random() < 0.7):
            spec["col"] = rnd.choice(["v", "o", "s", "w"])
        if f in ("lag", "lead"):
            spec["col"] = rnd.choice(["v", "o", "s", "w"])
            spec["offset"] = rnd.randint(1, 3)
            if rnd.random() < 0.5:
                spec["default"] = {"v": 0, "o": -1.0, "s": "none", "w": 0}[spec["col"]]
        cols[f"out{k}"] = spec
    p = {"columns": cols}
    if rnd.random() < 0.9 or any(c["func"] in ("row_number", "rank", "dense_rank", "lag", "lead", "cumsum",
                                                "cumcount", "cummin", "cummax") for c in cols.values()):
        p["order_by"] = order
    if part:
        p["partition_by"] = part
    return df, p


@pytest.mark.parametrize("seed", range(4))
def test_parity_with_duckdb(seed):
    pytest.importorskip("duckdb")
    from hydra_etl.internal.engines import large_volume as lv
    rnd = random.Random(seed)
    for _ in range(50):
        df, p = _random_case(rnd)
        step = {"window": p}
        expected = PandasEngine().apply_step(df.copy(), step).output
        d = lv.DuckGlobal()
        handed = []
        try:
            cut = rnd.randint(1, len(df))
            if df.iloc[:cut].isna().all().any():   # 1er lot sans type pour une colonne : un seul lot
                cut = len(df)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                d.append(df.iloc[:cut].reset_index(drop=True))
                if cut < len(df):
                    d.append(df.iloc[cut:].reset_index(drop=True))
                got = d.run([step], lambda x, rest, done: (handed.append(done),
                                                            PandasEngine().apply_step(x, rest[0]).output)[1])
        finally:
            d.close()
        assert not handed, f"window should run in DuckDB: {p}"
        # colonne d'entrée Int64 : rendue en int64 par DuckDB (comme pour sort / aggregate)
        expected["w"] = expected["w"].astype("int64")
        # sommes et moyennes en flottants : ordre d'addition propre à chaque moteur
        pd.testing.assert_frame_equal(expected.reset_index(drop=True), got.reset_index(drop=True),
                                      check_dtype=True, check_exact=False, rtol=1e-9, obj=str(p))


def _job(tmp: Path, steps: str) -> Path:
    job = tmp / "job"
    (job / "data").mkdir(parents=True)
    rows = "".join(f"{i},C{i % 7},{(i * 37) % 100},{i % 13}\n" for i in range(600))
    (job / "data" / "in.csv").write_text("id,cust,day,amount\n" + rows, encoding="utf-8")
    (job / "sources.yaml").write_text(
        "sources:\n  src:\n    type: csv\n    extract:\n      table: data/in.csv\n      batch_size: 100\n",
        encoding="utf-8")
    (job / "destinations.yaml").write_text(
        "destinations:\n  dst:\n    type: csv\n    load:\n      table: data/out.csv\n      mode: replace\n",
        encoding="utf-8")
    (job / "pipeline.yaml").write_text("pipeline:\n  from: src\n  to: dst\n", encoding="utf-8")
    (job / "transformations.yaml").write_text("steps:\n" + steps, encoding="utf-8")
    return job


WINDOW_JOB = """  - cast: {mapping: {day: int, amount: int}}
  - window:
      partition_by: [cust]
      order_by: [{col: day, desc: false}]
      columns:
        rn: {func: row_number}
        rk: {func: rank}
        prev: {func: lag, col: amount, default: 0}
        nxt: {func: lead, col: amount}
        running: {func: cumsum, col: amount}
        total: {func: sum, col: amount}
        last_day: {func: last, col: day}
"""


def test_job_window_pandas_duckdb_same_output(tmp_path, monkeypatch):
    pytest.importorskip("duckdb")
    pytest.importorskip("pyarrow")
    out = {}
    for engine in ("pandas", "duckdb"):
        monkeypatch.setenv("HYDRA_ENGINE", engine)
        job = _job(tmp_path / engine, WINDOW_JOB)
        r = JobExecutor(job_dir=str(job)).run()
        assert r.success, r.error
        out[engine] = (job / "data" / "out.csv").read_text(encoding="utf-8")
    assert out["pandas"] == out["duckdb"]
    df = pd.read_csv(tmp_path / "pandas" / "job" / "data" / "out.csv")
    assert len(df) == 600 and df.groupby("cust")["rn"].max().tolist() == [86, 86, 86, 86, 86, 85, 85]
