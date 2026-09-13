"""
frame_copy.py — copie paresseuse des DataFrames entre opérations.

Le problème
-----------
Chaque opération du moteur commence par `df.copy()` pour garantir qu'elle
ne modifie pas le DataFrame reçu. Sous pandas 2 sans Copy-on-Write, cette
copie est réelle : ~160 ms par million de lignes **et par opération**. Un
pipeline de cinq étapes paie donc ~800 ms de copies pures.

La solution
-----------
`copy(deep=None)` est une copie *paresseuse* quand le mode Copy-on-Write
est actif : rien n'est dupliqué tant que personne n'écrit, et la première
écriture ne recopie que la colonne touchée. La garantie de non-mutation
est strictement la même — c'est pandas qui la fait respecter.

Copy-on-Write est le comportement obligatoire de pandas 3, sur lequel
Hydra est déjà testé. `copy_on_write()` ne fait donc qu'aligner pandas 2
sur ce comportement déjà validé, et seulement pendant l'exécution d'un
job (option restaurée ensuite).

Désactivation : HYDRA_COW=0 — on retombe alors exactement sur le
comportement d'avant (copies réelles).
"""

from __future__ import annotations

import contextlib
import os
from typing import Any, ContextManager

import pandas as pd

_OFF = {"0", "false", "no", "off"}

try:
    _PANDAS_MAJOR = int(str(pd.__version__).split(".")[0])
except Exception:  # version exotique : on reste prudent
    _PANDAS_MAJOR = 2

# pandas peut retirer deep=None dans une version future : on teste une fois.
try:
    pd.DataFrame({"a": [1]}).copy(deep=None)
    _LAZY_COPY_SUPPORTED = True
except Exception:
    _LAZY_COPY_SUPPORTED = False


def cow_requested() -> bool:
    """Copy-on-Write demandé (défaut) sauf HYDRA_COW=0."""
    return os.environ.get("HYDRA_COW", "1").strip().lower() not in _OFF


def copy_on_write() -> ContextManager[Any]:
    """Contexte activant Copy-on-Write le temps d'un job (pandas 2 uniquement).

    Sous pandas >= 3, CoW est déjà le comportement par défaut : rien à faire.
    """
    if _PANDAS_MAJOR >= 3 or not cow_requested():
        return contextlib.nullcontext()
    try:
        return pd.option_context("mode.copy_on_write", True)
    except Exception:
        return contextlib.nullcontext()


def lazy_copy(df: pd.DataFrame) -> pd.DataFrame:
    """Copie d'un DataFrame destinée à être modifiée colonne par colonne.

    Paresseuse sous Copy-on-Write, réelle sinon. Dans les deux cas, le
    DataFrame reçu n'est jamais modifié.
    """
    if _LAZY_COPY_SUPPORTED:
        return df.copy(deep=None)
    return df.copy()
