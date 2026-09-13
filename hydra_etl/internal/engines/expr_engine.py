"""
expr_engine.py — choix du moteur d'expression pour `filter` et `calculate`.

Le gain
-------
`df.query(...)` et `df.eval(...)` acceptent deux moteurs : `python`
(numpy, un tableau temporaire par opération) et `numexpr` (évaluation par
blocs, sans temporaires, multi-thread). Mesuré ici (pandas 2.3.3, 2 cœurs) :

    a * b + c * d - a / (c + 1) + b * d * 2   1M lignes   35,3 -> 17,2 ms  (x2,05)
    (a * b + c * d - a / (c + 1)) > 0.8       1M lignes   31,4 -> 17,4 ms  (x1,80)
    a > 0.5                                   1M lignes   21,9 -> 23,7 ms  (x0,93)
    expression lourde                          10k lignes   2,9 ->  3,2 ms  (x0,90)

numexpr gagne donc sur les expressions *arithmétiques* et les gros
volumes, et perd ailleurs — d'où un garde-fou, pas un basculement.

La limite, mesurée
------------------
**numexpr n'est pas identique au bit près sur les flottants.** Sur 300
expressions aléatoires, 11 donnent un dernier chiffre différent (par ex.
1.4223803591605151e+20 contre 1.422380359160515e+20) : l'évaluation par
blocs ne réassocie pas les opérations comme numpy. Sur des colonnes
**int64** en revanche, 800 expressions (+ - *) et 400 filtres n'ont
montré **aucun écart**, valeur comme dtype.

Hydra tient une parité stricte (cf. l'écriture CSV en Rust, comparée
octet par octet). Le comportement par défaut suit donc la même règle :

    HYDRA_NUMEXPR non défini ou "1"  -> numexpr seulement là où le
                                        résultat est identique au bit près
                                        (colonnes int64, + - * uniquement)
    HYDRA_NUMEXPR=all                -> également sur les flottants et la
                                        division : plus rapide, mais le
                                        dernier chiffre peut changer
    HYDRA_NUMEXPR=0                  -> jamais (comportement d'avant)

Le garde-fou
------------
numexpr n'est demandé que si :

1. numexpr est installé ;
2. au moins `min_ops` opérations arithmétiques (défaut 3) ;
3. au moins `min_rows` lignes (défaut 50 000) ;
4. l'expression ne contient que des noms, des nombres, les opérateurs
   autorisés, des comparaisons et des connecteurs logiques — ni appel de
   fonction, ni chaîne, ni `**`, `%`, `//` ;
5. toutes les colonnes citées ont un dtype numpy éligible. Les dtypes
   d'extension (Int64, Float64, string...) sont exclus : pandas repasse
   alors lui-même en `python` avec un avertissement.

Tout refus rend `"python"` : exactement le comportement d'avant. Si
numexpr échoue malgré tout, l'appelant réessaie en `python`, et le
message d'erreur reste celui du moteur d'origine.

Réglages : HYDRA_NUMEXPR_MIN_ROWS (défaut 50000), HYDRA_NUMEXPR_MIN_OPS (défaut 3).
"""

from __future__ import annotations

import ast
import os
from typing import Any, Set, Tuple

import numpy as np
import pandas as pd

_OFF = {"0", "false", "no", "off"}
_ALL = {"all", "float", "floats", "2"}

try:  # dépendance optionnelle de pandas
    import numexpr as _numexpr  # noqa: F401
    _NUMEXPR_AVAILABLE = True
except Exception:
    _NUMEXPR_AVAILABLE = False

_EXACT_ARITH = (ast.Add, ast.Sub, ast.Mult)          # exacts sur les entiers
_ALL_ARITH = (ast.Add, ast.Sub, ast.Mult, ast.Div)

_COMMON_NODES = (
    ast.Expression, ast.Load,
    ast.BoolOp, ast.And, ast.Or,
    ast.UnaryOp, ast.Not, ast.USub, ast.UAdd, ast.Invert,
    ast.BinOp, ast.Add, ast.Sub, ast.Mult,
    ast.BitAnd, ast.BitOr, ast.BitXor,
    ast.Compare, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq, ast.NotEq,
    ast.Name, ast.Constant,
)
_NODES_EXACT = _COMMON_NODES
_NODES_ALL = _COMMON_NODES + (ast.Div,)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


def numexpr_mode() -> str:
    """"off" | "exact" (défaut) | "all"."""
    raw = os.environ.get("HYDRA_NUMEXPR", "1").strip().lower()
    if raw in _OFF:
        return "off"
    if raw in _ALL:
        return "all"
    return "exact"


def _eligible_dtype(dtype: Any, mode: str) -> bool:
    """dtype numpy accepté par le mode (jamais un dtype d'extension pandas)."""
    if not isinstance(dtype, np.dtype):
        return False
    if mode == "all":
        return dtype.kind in "biuf"
    # mode exact : uniquement int64 — les entiers plus courts sont promus en
    # int64 par numexpr (mêmes valeurs, dtype différent), les flottants ne
    # sont pas identiques au bit près.
    return dtype.kind == "i" and dtype.itemsize == 8


def _scan(expr: str, mode: str) -> Tuple[int, Set[str]] | None:
    """(nombre d'opérations arithmétiques, noms cités) ou None si non éligible."""
    allowed = _NODES_ALL if mode == "all" else _NODES_EXACT
    arith_ops = _ALL_ARITH if mode == "all" else _EXACT_ARITH
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return None  # `@variable`, backticks... : hors périmètre

    arith = 0
    names: Set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, allowed):
            return None
        if isinstance(node, ast.BinOp) and isinstance(node.op, arith_ops):
            arith += 1
        elif isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Constant) and not isinstance(node.value, (int, float, bool)):
            return None
    return arith, names


def choose_expr_engine(df: pd.DataFrame, expr: str) -> str:
    """Rend "numexpr" si le calcul y est identique et plus rapide, sinon "python"."""
    mode = numexpr_mode()
    if mode == "off" or not _NUMEXPR_AVAILABLE:
        return "python"
    if len(df) < _env_int("HYDRA_NUMEXPR_MIN_ROWS", 50_000):
        return "python"

    scanned = _scan(expr, mode)
    if scanned is None:
        return "python"
    arith, names = scanned
    if arith < _env_int("HYDRA_NUMEXPR_MIN_OPS", 3) or not names:
        return "python"

    columns = set(map(str, df.columns))
    for name in names:
        if name not in columns or not _eligible_dtype(df[name].dtype, mode):
            return "python"
    return "numexpr"
