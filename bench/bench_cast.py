"""Coût réel de l'opération `cast`, type par type, et coût de la copie.

Mesure le temps d'un seul appel à `_op_cast` sur N lignes, colonne par colonne,
avec les données telles qu'elles sortent d'une lecture CSV (chaînes).
"""
from __future__ import annotations

import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from hydra_etl.internal.engines.pandas_engine import PandasEngine  # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 1_000_000
rng = np.random.default_rng(0)


def frame() -> pd.DataFrame:
    return pd.DataFrame({
        "i": pd.array([str(v) for v in rng.integers(0, 10_000, N)], dtype="string"),
        "f": pd.array([f"{v:.4f}" for v in rng.random(N)], dtype="string"),
        "s": pd.array([f"v{v}" for v in rng.integers(0, 100, N)], dtype="string"),
        "b": pd.array(rng.choice(["true", "false", "yes", "non", "1"], N), dtype="string"),
        "d": pd.array(rng.choice(["2026-01-15", "2026-06-30", "2025-12-01"], N), dtype="string"),
    })


def timed(label, fn, n=1):
    best = min(_run(fn) for _ in range(n))
    print(f"{label:<28} {best*1000:8.1f} ms")
    return best


def _run(fn):
    t = time.perf_counter()
    fn()
    return time.perf_counter() - t


eng = PandasEngine.__new__(PandasEngine)   # pas d'état nécessaire pour _op_cast
df = frame()
print(f"N = {N:,} lignes, pandas {pd.__version__}\n")

timed("df.copy() seul", lambda: df.copy())
for col, typ in [("i", "int"), ("f", "float"), ("s", "str"), ("b", "bool"), ("d", "datetime")]:
    timed(f"cast {col} -> {typ}", lambda c=col, t=typ: eng._op_cast(df, {"mapping": {c: t}}))
timed("cast 5 colonnes", lambda: eng._op_cast(df, {"mapping": {
    "i": "int", "f": "float", "s": "str", "b": "bool", "d": "datetime"}}))

# Détail bool : la conversion seule, sans la copie du DataFrame
timed("_cast_to_bool seul", lambda: eng._cast_to_bool(df["b"]))
timed("to_datetime seul", lambda: pd.to_datetime(df["d"], errors="raise"))
timed("to_datetime format=", lambda: pd.to_datetime(df["d"], format="%Y-%m-%d", errors="raise"))
