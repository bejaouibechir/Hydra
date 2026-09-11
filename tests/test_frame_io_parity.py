"""
Parité du chemin DataFrame (étape 0-bis) avec le chemin historique list[dict].

Couvre :
- CSVConnector.extract_frames == pd.DataFrame(lot) d'extract_batches
- FrameBatch == df.to_dict("records") (types et valeurs)
- CSVConnector.load_batches : FrameBatch et list[dict] écrivent les mêmes octets
- JobExecutor : opérations globales sur l'ensemble des lignes, sorties
  identiques avec HYDRA_FRAME_IO=0 et HYDRA_FRAME_IO=1

Exécutable aussi sans pytest : `python tests/test_frame_io_parity.py`.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from hydra_etl.internal.connector.csv_connector import CSVConnector
from hydra_etl.internal.connector.frame_batch import FrameBatch

HEADER = "order_id,customer,category,price,qty,status,note\n"

CSV_CASES = {
    "regular": HEADER + "".join(
        f"{i},C{i:03d},{['A', 'B', 'C'][i % 3]},{i * 1.5},{i % 4},{['ok', 'ko'][i % 2]},n{i}\n" for i in range(250)
    ),
    "empty_cells_and_quotes": HEADER
    + '1,C1,A,,2,ok,"hello, world"\n'
    + '2,,B,3.5,,ko,"quote ""inside"""\n'
    + "3,C3,C,4.0,1,ok,\n"
    + "4,C4,A,1e3,0,ok,Zoë ünïcode\n",
    "blank_lines": HEADER + "1,C1,A,1,1,ok,x\n\n2,C2,B,2,2,ko,y\n\n\n3,C3,C,3,3,ok,z\n",
    "short_rows": HEADER + "1,C1,A,1,1,ok,x\n2,C2\n3,C3,C,3,3,ok,z\n",
    "long_rows": HEADER + "1,C1,A,1,1,ok,x,EXTRA,MORE\n2,C2,B,2,2,ko,y\n",
    "duplicate_header": "a,b,a\n1,2,3\n4,5,6\n",
    "semicolon": HEADER.replace(",", ";") + "1;C1;A;1,5;1;ok;x\n",
}


def _write(tmp: Path, name: str, content: str) -> Path:
    p = tmp / f"{name}.csv"
    p.write_text(content, encoding="utf-8", newline="")
    return p


def test_extract_frames_matches_extract_batches(tmp_path):
    for name, content in CSV_CASES.items():
        path = _write(tmp_path, name, content)
        cfg = {"delimiter": ";"} if name == "semicolon" else {}
        for bs in (1, 2, 100, 10_000):
            c = CSVConnector(name="src", config=dict(cfg))
            legacy = [pd.DataFrame(b) for b in c.extract_batches(table=str(path), batch_size=bs)]
            frames = list(c.extract_frames(table=str(path), batch_size=bs))
            assert len(legacy) == len(frames), (name, bs)
            for a, b in zip(legacy, frames):
                pd.testing.assert_frame_equal(a, b, check_dtype=True, obj=f"{name}/bs={bs}")


def test_extract_frames_same_errors(tmp_path):
    c = CSVConnector(name="src", config={})
    for kwargs in ({"table": str(tmp_path / "missing.csv")},
                   {"table": str(tmp_path)},
                   {"table": "x.csv", "query": "select 1"},
                   {"table": "x.csv", "batch_size": 0}):
        msgs = []
        for fn in (c.extract_batches, c.extract_frames):
            try:
                list(fn(**kwargs))
                msgs.append(None)
            except ValueError as e:
                msgs.append(str(e).split("CWD actuel")[0])
        assert msgs[0] is not None and msgs[0] == msgs[1], kwargs


def _typed_frame() -> pd.DataFrame:
    n = 6
    return pd.DataFrame({
        "i64": np.arange(n, dtype="int64"),
        "f64": [1.5, np.nan, 3.0, 1e20, -0.1, 2.0],
        "b": [True, False] * 3,
        "obj": ["a", None, "c", "", "e", "f"],
        "obj_np": pd.Series([np.int64(1), np.float64(2.5), "x", None, np.bool_(True), 3], dtype=object),
        "Int64": pd.array([1, None, 3, 4, None, 6], dtype="Int64"),
        "boolean": pd.array([True, None, False, True, None, False], dtype="boolean"),
        "string": pd.array(["x", None, "z", "", "w", "v"], dtype="string"),
        "Float64": pd.array([1.5, None, 2.5, 3.5, None, 0.0], dtype="Float64"),
        "cat": pd.Categorical(["u", None, "v", "u", "v", None]),
        "dt": pd.to_datetime(["2024-01-15", None, "2024-02-01 10:30", "2024-03-01", None, "2024-04-01"], format="ISO8601"),
    })


def test_frame_batch_equals_to_dict():
    df = _typed_frame()
    fb = FrameBatch.wrap(df)
    assert fb is not None
    expected = df.to_dict("records")
    got = list(fb)
    assert len(got) == len(expected) == len(fb)
    for e, g in zip(expected, got):
        assert list(e) == list(g)
        for k in e:
            ev, gv = e[k], g[k]
            assert type(ev) is type(gv), (k, ev, gv)
            assert ev == gv or (ev != ev and gv != gv) or (ev is pd.NaT and gv is pd.NaT), (k, ev, gv)
    assert [list(r) for r in fb[1:3]] == [list(r) for r in expected[1:3]]
    assert repr(fb[4]) == repr(expected[4]) and repr(fb[-1]) == repr(expected[-1])
    assert FrameBatch.wrap(pd.DataFrame([[1, 2]], columns=["a", "a"])) is None


def test_csv_load_same_bytes(tmp_path):
    df = _typed_frame()
    for mode in ("replace", "append"):
        outs = []
        for kind in ("dicts", "frame"):
            p = tmp_path / f"out_{mode}_{kind}.csv"
            if mode == "append":
                p.write_text("", encoding="utf-8")
            c = CSVConnector(name="dst", config={})
            m = mode
            for chunk in (df.iloc[:4], df.iloc[4:]):
                batch = chunk.to_dict("records") if kind == "dicts" else FrameBatch.wrap(chunk)
                c.load_batches([batch], table=str(p), mode=m)
                m = "append"
            outs.append(p.read_bytes())
        assert outs[0] == outs[1], mode


def _make_job(tmp: Path, name: str, data: Path, steps_yaml: str, bs: int) -> Path:
    d = tmp / name
    d.mkdir()
    (d / "sources.yaml").write_text(
        f'version: "1.0"\nsources:\n  src:\n    type: csv\n    connection: {{}}\n'
        f'    extract:\n      table: "{data.as_posix()}"\n      batch_size: {bs}\n', encoding="utf-8")
    (d / "destinations.yaml").write_text(
        'version: "1.0"\ndestinations:\n  dst:\n    type: csv\n    connection: {}\n'
        '    load:\n      table: ./output/out.csv\n      mode: replace\n', encoding="utf-8")
    (d / "pipeline.yaml").write_text('version: "1.0"\npipeline:\n  from: src\n  to: dst\n', encoding="utf-8")
    (d / "transformations.yaml").write_text('version: "1.0"\ntransformations:\n  steps:\n' + steps_yaml,
                                            encoding="utf-8")
    return d


STREAM_STEPS = """    - cast:
        mapping: {price: float, qty: int}
    - filter:
        expr: "status == 'ok'"
    - calculate:
        column: revenue
        expr: "price * qty"
"""
GLOBAL_STEPS = STREAM_STEPS + """    - aggregate:
        by: [category]
        agg:
          total: {func: sum, col: revenue}
          n: {func: count, col: order_id}
          avg: {func: mean, col: price}
    - sort:
        by: [total]
        ascending: false
"""


def _run_job(job: Path, frame_io: str):
    from hydra_etl.internal.runner.executor import JobExecutor
    old = os.environ.get("HYDRA_FRAME_IO")
    os.environ["HYDRA_FRAME_IO"] = frame_io
    try:
        r = JobExecutor(job).run()
    finally:
        if old is None:
            os.environ.pop("HYDRA_FRAME_IO", None)
        else:
            os.environ["HYDRA_FRAME_IO"] = old
    assert r.success, r.error
    return r, (job / "output" / "out.csv").read_bytes()


def test_executor_global_ops_and_frame_io(tmp_path):
    data = _write(tmp_path, "sales", CSV_CASES["regular"])
    outputs = {}
    for label, steps in (("stream", STREAM_STEPS), ("global", GLOBAL_STEPS)):
        for bs in (100, 100_000):
            for fio in ("0", "1"):
                job = _make_job(tmp_path, f"{label}_{bs}_{fio}", data, steps, bs)
                r, out = _run_job(job, fio)
                outputs[(label, bs, fio)] = (r.rows_in, r.rows_out, out)
    for label in ("stream", "global"):
        ref = outputs[(label, 100_000, "0")]          # un seul batch, chemin historique
        for key, val in outputs.items():
            if key[0] == label:
                assert val == ref, key
    assert outputs[("global", 100, "1")][1] == 3      # 3 catégories, pas 3 × nb_batches


if __name__ == "__main__":
    import inspect
    import sys
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            with tempfile.TemporaryDirectory() as t:
                try:
                    fn(Path(t)) if inspect.signature(fn).parameters else fn()
                    print("PASS", name)
                except Exception as e:  # noqa: BLE001
                    failed += 1
                    print("FAIL", name, type(e).__name__, e)
    sys.exit(1 if failed else 0)
