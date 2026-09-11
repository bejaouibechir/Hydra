"""
Parity between hydra_native.CsvBatchReader and Python's csv module, as used by
CSVConnector.extract_frames: header = first record, blank rows skipped, same
batch boundaries, same values. Randomized (fuzz) and targeted cases.

Run: python -m pytest rust/hydra_native/tests -q   (or: python this_file.py)
"""
from __future__ import annotations

import csv
import os
import random
import tempfile

import pandas as pd
import pyarrow as pa

import hydra_native as hn


def python_reference(path, delimiter, quotechar, batch_size):
    """(header, [batch_rows...]) exactly as extract_frames reads them, or raises."""
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f, delimiter=delimiter, quotechar=quotechar)
        header = next(reader, None)
        batches, rows = [], []
        for row in reader:
            if row == []:
                continue
            rows.append(row)
            if len(rows) >= batch_size:
                batches.append(rows)
                rows = []
        if rows:
            batches.append(rows)
    return header, batches


def rust_read(path, delimiter, quotechar, batch_size):
    r = hn.CsvBatchReader(path, delimiter=delimiter, quotechar=quotechar, batch_size=batch_size)
    batches, kinds = [], []
    for b in r:
        if isinstance(b, list):
            batches.append(b)
            kinds.append("rows")
        else:
            assert isinstance(b, pa.RecordBatch)
            cols = [c.to_pylist() for c in b.columns]
            batches.append([list(t) for t in zip(*cols)])
            kinds.append("columns")
            # pandas view must equal the one built by extract_frames from Python lists
            d = {n: c for n, c in zip(b.schema.names, cols)}
            pd.testing.assert_frame_equal(b.to_pandas(), pd.DataFrame(d, columns=list(d)), check_dtype=True)
    return r.header, batches, kinds, r.rows_emitted


def compare(content: str, delimiter=",", quotechar='"', batch_size=3):
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8", newline="") as f:
        f.write(content)
        path = f.name
    try:
        try:
            ref = python_reference(path, delimiter, quotechar, batch_size)
            ref_err = None
        except csv.Error as e:
            ref, ref_err = None, e
        try:
            got = rust_read(path, delimiter, quotechar, batch_size)
        except hn.CsvFallback as e:
            return "fallback", str(e.args[0])
        if ref_err is not None:
            raise AssertionError(f"Python raised {ref_err!r}, Rust did not: {content!r}")
        header, batches, kinds, emitted = got
        assert header == ref[0], (content, header, ref[0])
        if header:
            assert batches == ref[1], (content, batches, ref[1])
            assert emitted == sum(map(len, ref[1]))
            n = len(header)
            for b, k in zip(batches, kinds):
                regular = len(set(header)) == n and all(len(r) == n for r in b)
                assert (k == "columns") == regular, (content, k)
        return "ok", None
    finally:
        os.unlink(path)


TARGETED = [
    "a,b\n1,2\n", "a,b\r\n1,2\r\n", "a,b\r1,2\r", "a,b\n\n1,2\n\n\n3,4", "a,b\n1\n2,3,4\n",
    'a,b\n"x,y","z""q"\n', 'a,b\n"multi\nline",2\n', 'a,b\nx"y,2\n', 'a,b\n"ab"cd,2\n',
    "\na,b\n1,2\n", "", "a,b", "a,b,a\n1,2,3\n", "é,€\nñ,ü\n", "a;b\n1;2\n",
    'a,b\n1,"unterminated\n', "a,b\n1,2", "a,b\n,\n", "a,b\n\"\",\"\"\n",
]


def test_targeted():
    for c in TARGETED:
        for d in (",", ";"):
            for bs in (1, 2, 100):
                compare(c, delimiter=d, batch_size=bs)


def test_fuzz():
    rng = random.Random(20260911)
    alphabet = ["a", "b", "1", ",", ";", '"', "'", "\n", "\r", "\r\n", " ", "é", "€", "\t"]
    stats = {"ok": 0, "fallback": 0}
    for _ in range(6000):
        content = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 60)))
        d = rng.choice([",", ";"])
        q = rng.choice(['"', "'"])
        status, _ = compare(content, delimiter=d, quotechar=q, batch_size=rng.choice([1, 2, 5, 100]))
        stats[status] += 1
    # Fallbacks are only legitimate when a quoted field is left open at EOF.
    assert stats["fallback"] < stats["ok"], stats
    print("fuzz", stats)


if __name__ == "__main__":
    test_targeted()
    test_fuzz()
    print("PASS")
