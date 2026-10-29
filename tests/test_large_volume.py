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
    assert lv.requested_engine() == ("auto", "engine: auto")
    assert lv.requested_engine("duckdb") == ("duckdb", "engine: duckdb")
    monkeypatch.setenv("HYDRA_ENGINE", "Pandas")
    assert lv.requested_engine("duckdb") == ("pandas", "HYDRA_ENGINE=pandas")   # variable prioritaire
    monkeypatch.setenv("HYDRA_ENGINE", "spark")
    with pytest.raises(ValueError, match="inconnu"):
        lv.requested_engine()


def test_engine_key_parsed():
    from hydra_etl.internal.parser.transform import TransformParser
    one = [{"sort": {"by": ["a"]}}]
    assert TransformParser().parse({"steps": one}).engine == "auto"
    assert TransformParser().parse({"engine": "DuckDB", "steps": one}).engine == "duckdb"
    assert TransformParser().parse({"transformations": {"engine": "pandas", "steps": one}}).engine == "pandas"
    with pytest.raises(Exception, match="engine"):
        TransformParser().parse({"engine": "spark", "steps": one})


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


def _job(tmp: Path, steps: str, engine: str = "") -> Path:
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
    (job / "transformations.yaml").write_text(engine + "steps:\n" + steps, encoding="utf-8")
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


@pytest.mark.parametrize("head, expected", [
    ("engine: duckdb\n", "duckdb"),
    ("transformations:\n  engine: duckdb\n", None),          # forme imbriquée : voir ci-dessous
    ("engine: pandas\n", "pandas"),
])
def test_engine_from_transformations_yaml(tmp_path, monkeypatch, head, expected):
    monkeypatch.delenv("HYDRA_ENGINE", raising=False)
    monkeypatch.setenv("HYDRA_LARGE_VOLUME_ROWS", "1000")         # auto choisirait duckdb
    if expected is None:                                           # forme écrite par Studio
        job = _job(tmp_path, "")
        steps = "\n".join("  " + ln if ln else ln for ln in AGG.splitlines())
        (job / "transformations.yaml").write_text(head + "  steps:\n" + steps + "\n", encoding="utf-8")
        expected = "duckdb"
    else:
        job = _job(tmp_path, AGG, engine=head)
    ex = JobExecutor(job_dir=str(job))
    assert ex.run().success
    assert ex.engine == expected and ex.engine_reason == f"engine: {expected}"
    monkeypatch.setenv("HYDRA_ENGINE", "pandas")                   # la variable l'emporte
    ex = JobExecutor(job_dir=str(job))
    assert ex.run().success and ex.engine == "pandas"


# ── join right / outer dans DuckDB ──────────────────────────────────────────
def _random_join_case(rnd):
    import random  # noqa: F401
    keytype = rnd.choice(["str", "int"])
    nk = rnd.choice([1, 1, 2])
    kv = (lambda: str(rnd.randint(0, 6))) if keytype == "str" else (lambda: rnd.randint(0, 6))
    nl, nr = rnd.randint(1, 40), rnd.randint(1, 12)
    left = pd.DataFrame({**{f"k{i}": [kv() for _ in range(nl)] for i in range(nk)},
                         "v": [rnd.randint(0, 9) for _ in range(nl)],
                         "amount": [round(rnd.uniform(0, 100), 2) for _ in range(nl)],
                         "x": [f"l{j}" for j in range(nl)],
                         "b": [rnd.random() < .5 for _ in range(nl)]})
    keys = [f"k{i}" for i in range(nk)]
    rows = [{**{f"k{i}": kv() for i in range(nk)}, "x": f"r{j}", "country": rnd.choice(["FR", "TN", "DE"]),
             "n": rnd.randint(0, 9)} for j in range(nr)]
    how = rnd.choice(["right", "outer"])
    if rnd.random() < .5:
        jp = {"key": keys if nk > 1 else keys[0], "how": how}
    else:
        rows = [{("r" + k if k in keys else k): v for k, v in r.items()} for r in rows]
        jp = {"left_key": keys, "right_key": ["r" + k for k in keys], "how": how}
    jp["_right_rows"] = rows
    tail = rnd.choice([[], [{"sort": {"by": ["x"]}}], [{"fill_null": {"value": 0}}],
                       [{"aggregate": {"by": ["country"], "agg": {
                           "s": {"func": "sum", "col": "amount"}, "c": {"func": "count", "col": "x"},
                           "mx": {"func": "max", "col": "v"}}}}]])
    return left, [{"join": jp}] + tail


@pytest.mark.parametrize("seed", range(4))
def test_join_right_outer_parity(seed):
    """Mêmes lignes, colonnes, ordre et types que pandas (df.merge), clés texte ou
    entières, simples ou multiples, key ou left_key / right_key, colonnes en double
    (suffixe _r), lots multiples, suivis de sort / aggregate / fill_null."""
    import random
    import warnings
    from hydra_etl.internal.engines.pandas_engine import PandasEngine
    eng, rnd = PandasEngine(), random.Random(seed)

    def pandas_run(df, steps):
        for st in steps:
            df = eng.apply_step(df, st).output
        return df

    for _ in range(60):
        left, steps = _random_join_case(rnd)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            expected = pandas_run(left.copy(), steps)
            d = lv.DuckGlobal()
            handed = []
            try:
                d.keep_only(steps)
                cut = rnd.randint(1, len(left))
                d.append(left.iloc[:cut].reset_index(drop=True))
                d.append(left.iloc[cut:].reset_index(drop=True))
                got = d.run(steps, lambda df, rest, done: (handed.append(done), pandas_run(df, rest))[1])
            finally:
                d.close()
        assert not handed or handed[0] > 0, "la jointure doit être faite par DuckDB"
        agg = any("aggregate" in st for st in steps)
        # sommes : DuckDB (fsum) et pandas peuvent différer au dernier chiffre
        pd.testing.assert_frame_equal(expected.reset_index(drop=True), got.reset_index(drop=True),
                                      check_exact=not agg, rtol=1e-12)
        if not agg:
            assert expected.to_csv(index=False) == got.to_csv(index=False)


def test_join_falls_back_to_pandas_when_not_guaranteed():
    """Clés avec vides ou de types différents : pandas s'en charge (même résultat)."""
    left = pd.DataFrame({"k": ["a", None, "b"], "v": [1, 2, 3]})
    steps = [{"join": {"key": "k", "how": "outer", "_right_rows": [{"k": "a", "w": "x"}]}}]
    d = lv.DuckGlobal()
    handed = []
    try:
        d.append(left)
        d.run(steps, lambda df, rest, done: (handed.append(done), df)[1])
    finally:
        d.close()
    assert handed == [0]


JOIN_RIGHT = """  - filter: {expr: "status == 'paid'"}
  - cast: {mapping: {amount: float}}
  - join: {right: customers, key: customer, how: HOW}
  - aggregate:
      by: [country]
      agg:
        revenue: {func: sum, col: amount}
        orders: {func: count, col: id}
  - sort: {by: [revenue], ascending: false}
"""


@pytest.mark.parametrize("how", ["right", "outer"])
def test_job_join_right_outer_pandas_duckdb(tmp_path, monkeypatch, how):
    out = {}
    for engine in ("pandas", "duckdb"):
        monkeypatch.setenv("HYDRA_ENGINE", engine)
        job = _job(tmp_path / engine, JOIN_RIGHT.replace("HOW", how))
        (job / "data" / "customers.csv").write_text(
            "customer,country\n" + "".join(f"C{i},{'FR' if i % 2 else 'TN'}\n" for i in range(9)),
            encoding="utf-8")
        (job / "sources.yaml").write_text(
            (job / "sources.yaml").read_text(encoding="utf-8")
            + "  customers:\n    type: csv\n    extract:\n      table: data/customers.csv\n", encoding="utf-8")
        r = JobExecutor(job_dir=str(job)).run()
        assert r.success, r
        out[engine] = pd.read_csv(job / "data" / "out.csv", keep_default_na=False)
    pd.testing.assert_frame_equal(out["pandas"], out["duckdb"], check_exact=False, rtol=1e-12)


def test_sort_is_stable():
    from hydra_etl.internal.engines.pandas_engine import PandasEngine
    df = pd.DataFrame({"k": [1, 0] * 50, "i": range(100)})
    out = PandasEngine().apply_step(df, {"sort": {"by": ["k"]}}).output
    assert list(out["i"]) == list(range(1, 100, 2)) + list(range(0, 100, 2))
