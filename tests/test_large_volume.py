"""
Moteur gros volumes (large_volume.py + CSVConnector._extract_frames_arrow).

- Lecteur rapide (pyarrow) : mêmes DataFrames que le lecteur Python, y compris
  dans les cas où il rend la main (ligne irrégulière, BOM, en-tête dupliqué).
- Choix du moteur : HYDRA_ENGINE / seuil HYDRA_LARGE_VOLUME_ROWS.
- Parité des jobs : mêmes sorties avec engine pandas et duckdb.
"""
from __future__ import annotations

import warnings
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("duckdb")
pytest.importorskip("pyarrow")

from hydra_etl.internal.connector.csv_connector import CSVConnector  # noqa: E402
from hydra_etl.internal.engines import large_volume as lv  # noqa: E402
from hydra_etl.internal.runner.executor import JobExecutor  # noqa: E402

HEADER = "order_id,customer,category,price,qty,status,note\n"
CASES = {
    "regular": HEADER + "".join(
        f"{i},C{i:03d},{'ABC'[i % 3]},{i * 1.5},{i % 4},{['ok', 'ko'][i % 2]},n{i}\n" for i in range(250)),
    "empty_and_quotes": HEADER + '1,C1,A,,2,ok,"hello, world"\n2,,B,3.5,,ko,"quote ""in"""\n'
                                 "3,C3,C,4.0,1,ok,\n4,C4,A,1e3,0,ok,Zoë\n",
    "blank_lines": HEADER + "1,C1,A,1,1,ok,x\n\n2,C2,B,2,2,ko,y\n\n\n3,C3,C,3,3,ok,z\n",
    "short_rows": HEADER + "1,C1,A,1,1,ok,x\n2,C2\n3,C3,C,3,3,ok,z\n",
    "long_rows": HEADER + "1,C1,A,1,1,ok,x,EXTRA,MORE\n2,C2,B,2,2,ko,y\n",
    "duplicate_header": "a,b,a\n1,2,3\n4,5,6\n",
    "bom": "﻿" + HEADER + "1,C1,A,1,1,ok,x\n",
    "quoted_newline": HEADER + '1,C1,A,1,1,ok,"multi\nline"\n2,C2,B,2,2,ko,y\n',
    # ligne irrégulière après plusieurs blocs déjà rendus : reprise au bon endroit
    "late_irregular": HEADER + "".join(f"{i},C,A,1,1,ok,x\n" for i in range(60_000)) + "bad,row\n"
                      + "".join(f"{i},D,B,2,2,ko,y\n" for i in range(500)),
}


def _frames(gen) -> pd.DataFrame:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return pd.concat(list(gen), ignore_index=True)


@pytest.mark.parametrize("name", sorted(CASES))
def test_arrow_reader_matches_python_reader(tmp_path, name):
    p = tmp_path / f"{name}.csv"
    p.write_text(CASES[name], encoding="utf-8", newline="")
    c = CSVConnector(name="src", config={})
    ref = _frames(c.extract_frames(table=str(p), batch_size=10_000))
    fast = _frames(c._extract_frames_arrow(table=str(p), batch_size=10_000, block_mb=1))
    pd.testing.assert_frame_equal(ref, fast)


def test_requested_engine(monkeypatch):
    monkeypatch.delenv("HYDRA_ENGINE", raising=False)
    assert lv.requested_engine() == "auto"
    monkeypatch.setenv("HYDRA_ENGINE", "DuckDB")
    assert lv.requested_engine() == "duckdb"
    monkeypatch.setenv("HYDRA_ENGINE", "spark")
    with pytest.raises(ValueError, match="inconnu"):
        lv.requested_engine()


def test_decide_auto(tmp_path, monkeypatch):
    p = tmp_path / "x.csv"
    p.write_text("a,b\n" + "1,2\n" * 1000, encoding="utf-8")
    assert lv.decide("auto", False, p)[0] == "pandas"                  # pas d'opération globale
    monkeypatch.setenv("HYDRA_LARGE_VOLUME_ROWS", "100000")
    engine, reason = lv.decide("auto", True, p)
    assert engine == "pandas" and "<" in reason
    monkeypatch.setenv("HYDRA_LARGE_VOLUME_ROWS", "500")
    assert lv.decide("auto", True, p)[0] == "duckdb"
    assert lv.decide("pandas", True, p)[0] == "pandas"
    assert lv.estimate_csv_rows(p) == pytest.approx(1000, rel=0.01)


def _job(tmp: Path, steps: str) -> Path:
    job = tmp / "job"
    (job / "data").mkdir(parents=True)
    rows = "".join(
        f"{i},{['paid', 'refunded'][i % 5 == 0]},{(i * 37) % 1000 / 10},C{i % 7},"
        f"{'' if i % 11 == 0 else ['FR', 'DE', 'ES'][i % 3]}\n"
        for i in range(3000))
    (job / "data" / "in.csv").write_text("id,status,amount,customer,country\n" + rows, encoding="utf-8")
    (job / "sources.yaml").write_text(
        "sources:\n  src:\n    type: csv\n    extract:\n      table: data/in.csv\n      batch_size: 500\n",
        encoding="utf-8")
    (job / "destinations.yaml").write_text(
        "destinations:\n  dst:\n    type: csv\n    load:\n      table: data/out.csv\n      mode: replace\n",
        encoding="utf-8")
    (job / "pipeline.yaml").write_text("pipeline:\n  from: src\n  to: dst\n", encoding="utf-8")
    (job / "transformations.yaml").write_text("steps:\n" + steps, encoding="utf-8")
    return job


AGG = """  - filter: {expr: "status == 'paid'"}
  - cast: {mapping: {amount: float}}
  - aggregate:
      by: [country]
      agg:
        revenue: {func: sum, col: amount}
        orders: {func: count, col: id}
        low: {func: min, col: amount}
        high: {func: max, col: amount}
        avg: {func: mean, col: amount}
"""
SORT = """  - cast: {mapping: {amount: float}}
  - sort: {by: [amount, id], ascending: [false, true]}
"""
TAIL = AGG + """  - calculate: {column: revenue_k, expr: "revenue / 1000"}
  - sort: {by: [revenue], ascending: false}
"""


@pytest.mark.parametrize("steps", [AGG, SORT, TAIL], ids=["aggregate", "sort", "pandas_tail"])
def test_job_parity_pandas_duckdb(tmp_path, monkeypatch, steps):
    out = {}
    for engine in ("pandas", "duckdb"):
        monkeypatch.setenv("HYDRA_ENGINE", engine)
        job = _job(tmp_path / engine, steps)
        r = JobExecutor(job_dir=str(job)).run()
        assert r.success, r
        out[engine] = (job / "data" / "out.csv").read_bytes()
    assert out["pandas"] == out["duckdb"]          # mêmes octets, sommes comprises


def test_auto_engine_above_threshold(tmp_path, monkeypatch):
    monkeypatch.delenv("HYDRA_ENGINE", raising=False)
    monkeypatch.setenv("HYDRA_LARGE_VOLUME_ROWS", "1000")
    ex = JobExecutor(job_dir=str(_job(tmp_path / "big", AGG)))
    assert ex.run().success and ex.engine == "duckdb"
    monkeypatch.setenv("HYDRA_LARGE_VOLUME_ROWS", "2000000")
    ex = JobExecutor(job_dir=str(_job(tmp_path / "small", AGG)))
    assert ex.run().success and ex.engine == "pandas"
