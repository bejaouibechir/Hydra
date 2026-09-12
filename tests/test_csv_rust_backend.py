"""
Lecture CSV : le backend Rust (hydra_native) rend exactement les mêmes lots que
le backend Python, y compris quand il rend la main à Python en cours de lecture.

Ignoré si hydra_native ou pyarrow ne sont pas installés (Windows, installation
sans l'extra natif).
"""
from __future__ import annotations

import os
import warnings

import pandas as pd
import pytest

pytest.importorskip("pyarrow")
pytest.importorskip("hydra_native")

from hydra_etl import _backend  # noqa: E402
from hydra_etl.internal.connector.csv_connector import CSVConnector  # noqa: E402

from test_frame_io_parity import (  # noqa: E402
    CSV_CASES, GLOBAL_STEPS, STREAM_STEPS, _make_job, _write,
)

EXTRA_CASES = {
    "crlf": "a,b\r\n1,2\r\n3,4\r\n",
    "cr_only": "a,b\r1,2\r3,4\r",
    "multiline_quoted": 'a,b\n"line1\nline2",x\n"q ""q""",y\n',
    "no_trailing_newline": "a,b\n1,2\n3,4",
    "header_only": "a,b\n",
    # Rendus à Python : dès l'ouverture, puis en cours de lecture
    "bom": "﻿a,b\n1,2\n",
    "open_quote_at_eof": "a,b\n" + "".join(f"{i},v{i}\n" for i in range(25)) + '26,"never closed\n',
    "nul_byte": "a,b\n1,x\x00y\n",
}


def _frames(path, backend, bs, cfg):
    c = CSVConnector(name="src", config=dict(cfg))
    return list(c.extract_frames(table=str(path), batch_size=bs, backend=backend))


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    # Fichiers de test minuscules : on force le lecteur Rust malgré le seuil de taille.
    monkeypatch.setattr(CSVConnector, "rust_min_bytes", 0)
    monkeypatch.setattr(CSVConnector, "rust_min_write_rows", 0)
    _backend.reload()
    yield
    _backend.reload()


def test_small_files_use_python(tmp_path, monkeypatch):
    monkeypatch.setattr(CSVConnector, "rust_min_bytes", 1_000_000)
    path = _write(tmp_path, "small", CSV_CASES["regular"])
    import hydra_native
    monkeypatch.setattr(hydra_native, "CsvBatchReader", None)   # ne doit pas être appelé
    assert sum(len(f) for f in _frames(path, "rust", 100, {})) == 250


@pytest.mark.parametrize("name", sorted({**CSV_CASES, **EXTRA_CASES}))
@pytest.mark.parametrize("bs", [1, 2, 10, 10_000])
def test_rust_frames_equal_python_frames(tmp_path, name, bs):
    content = {**CSV_CASES, **EXTRA_CASES}[name]
    path = _write(tmp_path, name, content)
    cfg = {"delimiter": ";"} if name == "semicolon" else {}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # avertissements de repli attendus
        expected = _frames(path, "python", bs, cfg)
        got = _frames(path, "rust", bs, cfg)
    assert len(got) == len(expected)
    for a, b in zip(expected, got):
        pd.testing.assert_frame_equal(a, b, check_dtype=True)


def test_handover_is_announced(tmp_path):
    path = _write(tmp_path, "eof", EXTRA_CASES["open_quote_at_eof"])
    with pytest.warns(RuntimeWarning, match="handed"):
        frames = _frames(path, "rust", 10, {})
    assert sum(len(f) for f in frames) == 26


def test_same_errors(tmp_path):
    empty = tmp_path / "empty.csv"
    empty.write_text("", encoding="utf-8")
    blank_first = tmp_path / "blank.csv"
    blank_first.write_text("\na,b\n1,2\n", encoding="utf-8")
    for kwargs in ({"table": str(tmp_path / "missing.csv")}, {"table": str(empty)},
                   {"table": str(blank_first)}, {"table": "x.csv", "batch_size": 0}):
        msgs = []
        for backend in ("python", "rust"):
            try:
                list(CSVConnector(name="src", config={}).extract_frames(backend=backend, **kwargs))
                msgs.append(None)
            except ValueError as e:
                msgs.append(str(e).split("CWD actuel")[0])
        assert msgs[0] is not None and msgs[0] == msgs[1], kwargs


def _run(job, backend):
    from hydra_etl.internal.runner.executor import JobExecutor
    old = os.environ.get("HYDRA_BACKEND")
    os.environ["HYDRA_BACKEND"] = backend
    _backend.reload()
    try:
        r = JobExecutor(job).run()
    finally:
        if old is None:
            os.environ.pop("HYDRA_BACKEND", None)
        else:
            os.environ["HYDRA_BACKEND"] = old
        _backend.reload()
    assert r.success, r.error
    return r.rows_in, r.rows_out, (job / "output" / "out.csv").read_bytes()


@pytest.mark.parametrize("steps", [STREAM_STEPS, GLOBAL_STEPS], ids=["stream", "global"])
def test_job_output_identical(tmp_path, steps):
    data = _write(tmp_path, "sales", CSV_CASES["regular"])
    out = {b: _run(_make_job(tmp_path, f"job_{b}", data, steps, 100), b) for b in ("python", "rust")}
    assert out["python"] == out["rust"]


# --- écriture (opération csv.write) ---------------------------------------

def _write_frames(path, frames, backend, mode="replace", cfg=None):
    from hydra_etl.internal.connector.frame_batch import FrameBatch
    c = CSVConnector(name="dst", config=dict(cfg or {}))
    m = mode
    for f in frames:
        c.load_batches([FrameBatch.wrap(f)], table=str(path), mode=m, backend=backend)
        m = "append"
    return path.read_bytes()


def _typed_frames():
    """Cadres couvrant les types écrits par le moteur, plus des cas limites."""
    return [
        pd.DataFrame({
            "s": ["plain", 'say "hi"', "a,b", "line\nbreak", "cr\rreturn", "Zoë", ""],
            "i": pd.array([1, -2, 3, None, 5, 6, 7], dtype="Int64"),
            "f": [1.5, -0.1, 1e20, 1e-5, 0.0, 123456789.123, 2.0],
            "b": pd.array([True, False, None, True, False, True, False], dtype="boolean"),
        }),
        pd.DataFrame({"s": ["x"], "i": pd.array([9], dtype="Int64"), "f": [0.1], "b": [True]}),
        pd.DataFrame({"s": pd.Series([], dtype="str"), "i": pd.array([], dtype="Int64"),
                      "f": pd.Series([], dtype="float64"), "b": pd.array([], dtype="boolean")}),
    ]


@pytest.mark.parametrize("mode", ["replace", "append"])
@pytest.mark.parametrize("cfg", [{}, {"delimiter": ";", "quotechar": "'"}], ids=["comma", "semicolon"])
def test_rust_write_same_bytes(tmp_path, mode, cfg):
    frames = _typed_frames()
    out = {}
    for backend in ("python", "rust"):
        p = tmp_path / f"out_{mode}_{backend}_{len(cfg)}.csv"
        if mode == "append":
            p.write_text("", encoding="utf-8")
        out[backend] = _write_frames(p, frames, backend, mode=mode, cfg=cfg)
    assert out["python"] == out["rust"]


def test_small_writes_use_python(tmp_path, monkeypatch):
    monkeypatch.setattr(CSVConnector, "rust_min_write_rows", 1_000_000)
    import hydra_native
    monkeypatch.setattr(hydra_native, "write_csv", None)   # ne doit pas être appelé
    data = _write_frames(tmp_path / "small.csv", _typed_frames(), "rust")
    assert data.startswith(b"s,i,f,b")


def test_rust_write_falls_back_on_unsupported_types(tmp_path):
    """Dates, NaN dans une colonne float non nullable : le chemin Python reprend."""
    frames = [
        pd.DataFrame({"d": pd.to_datetime(["2024-01-15", "2024-02-01 10:30"], format="ISO8601"), "n": [1, 2]}),
        pd.DataFrame({"f": [1.5, float("nan")], "n": [1, 2]}),
        pd.DataFrame({"o": ["a", None], "n": [1, 2]}),
    ]
    for i, f in enumerate(frames):
        py = _write_frames(tmp_path / f"py{i}.csv", [f], "python")
        rs = _write_frames(tmp_path / f"rs{i}.csv", [f], "rust")
        assert py == rs, f.dtypes.to_dict()
