"""Coût d'un garde-fou « la colonne ne contient que des caractères décimaux ».

But : n'utiliser le chemin rapide (`astype`) que lorsqu'il est garanti d'accepter
exactement ce que `to_numeric` accepte. `astype` reconnaît en plus l'hexadécimal,
les tirets bas, « nan », « inf » et les chiffres non ASCII : tous exigent un
caractère hors de [0-9 + - . e E espaces].
"""
from __future__ import annotations

import re
import sys
import time

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc

N = int(sys.argv[1]) if len(sys.argv) > 1 else 1_000_000
rng = np.random.default_rng(0)
s_str = pd.Series(pd.array([f"{v:.4f}" for v in rng.random(N)], dtype="string"))
s_obj = s_str.astype(object)
ALLOWED = re.compile(r"[0-9+\-.eE \t\r\n]*\Z")


def timed(label, fn):
    t = time.perf_counter()
    out = fn()
    print(f"{label:<46} {(time.perf_counter()-t)*1000:8.1f} ms   -> {out}")


def join_scan(s):
    return bool(ALLOWED.match("".join(s.tolist())))


def cat_scan(s):
    return bool(ALLOWED.match(s.str.cat()))


def buffer_scan(s):
    arr = pa.array(s)
    if not pa.types.is_string(arr.type) and not pa.types.is_large_string(arr.type):
        return None
    buf = arr.buffers()[2]
    return bool(ALLOWED.match(memoryview(buf).tobytes().decode("ascii", "strict")))


def arrow_regex(s):
    arr = pa.array(s)
    return pc.all(pc.match_substring_regex(arr, r"^[0-9+\-.eE \t]*$")).as_py()


print(f"N = {N:,}  pandas {pd.__version__}  pyarrow {pa.__version__}")
for label, s in (("string", s_str), ("object", s_obj)):
    print(f"\n--- colonne {label} ---")
    timed("join + regex", lambda s=s: join_scan(s))
    timed("str.cat + regex", lambda s=s: cat_scan(s))
    timed("buffer arrow + regex", lambda s=s: buffer_scan(s))
    timed("pyarrow match_substring_regex", lambda s=s: arrow_regex(s))
    timed("astype('float64')", lambda s=s: s.astype("float64").sum())
    timed("arrow cast double", lambda s=s: len(pc.cast(pa.array(s), pa.float64())))
    timed("to_numeric (reference)", lambda s=s: pd.to_numeric(s, errors="raise").sum())
