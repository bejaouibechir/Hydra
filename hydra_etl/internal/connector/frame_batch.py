"""
FrameBatch — batch de sortie porté par un DataFrame (étape 0-bis).

Pourquoi
--------
Le chemin historique convertit chaque batch transformé en list[dict]
(`df.to_dict("records")`) puis le connecteur réécrit chaque dict ligne à ligne.
Sur un job CSV, ces deux conversions coûtent ~50 % du temps total.

FrameBatch se comporte comme une liste de dicts pour tout le code existant
(len, bool, indexation, tranches → list[dict]) mais permet à un connecteur qui
le sait (`accepts_frame_batches = True`) d'écrire les valeurs colonne par
colonne, sans créer un dict par ligne.

Parité
------
`rows()` rend, ligne par ligne, exactement les valeurs que rendrait
`df.to_dict("records")` (mêmes types, mêmes valeurs). Les DataFrames pour
lesquels ce n'est pas garanti ne sont pas enveloppés (`can_wrap` → False) et
passent par le chemin historique. Vérifié par tests/test_frame_io_parity.py.

Désactivation : variable d'environnement HYDRA_FRAME_IO=0.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Iterator, List, Tuple

import numpy as np
import pandas as pd


def frame_io_enabled() -> bool:
    """Chemin DataFrame actif sauf si HYDRA_FRAME_IO vaut 0/false/no/off."""
    return os.environ.get("HYDRA_FRAME_IO", "1").strip().lower() not in {"0", "false", "no", "off"}


def _column_values(s: pd.Series) -> List[Any] | None:
    """Valeurs Python d'une colonne, identiques à celles de to_dict('records').
    None si la parité n'est pas garantie pour cette colonne."""
    vals = s.tolist()
    if s.dtype == object:
        if any(isinstance(v, (np.datetime64, np.timedelta64)) for v in vals):
            return None
        if any(isinstance(v, np.generic) for v in vals):
            # to_dict « boxe » les scalaires numpy des colonnes object
            vals = [v.item() if isinstance(v, np.generic) else v for v in vals]
    if isinstance(s.dtype, pd.api.extensions.ExtensionDtype) and s.hasnans:
        # to_dict rend None là où tolist() rend pd.NA (Int64, boolean, string, Float64)
        vals = [None if v is pd.NA else v for v in vals]
    return vals


class FrameBatch:
    """Vue « liste de dicts » d'un DataFrame, sans matérialiser les dicts."""

    __slots__ = ("frame", "_columns", "_cols")

    def __init__(self, frame: pd.DataFrame, cols: List[List[Any]]) -> None:
        self.frame = frame
        self._columns = frame.columns.tolist()
        self._cols = cols

    @classmethod
    def wrap(cls, frame: pd.DataFrame) -> "FrameBatch | None":
        """FrameBatch si la parité avec to_dict('records') est garantie, sinon None."""
        if not isinstance(frame, pd.DataFrame) or not frame.columns.is_unique:
            return None
        cols: List[List[Any]] = []
        for _, s in frame.items():
            v = _column_values(s)
            if v is None:
                return None
            cols.append(v)
        return cls(frame, cols)

    # --- protocole « liste de dicts » utilisé par l'executor et les connecteurs ---
    def __len__(self) -> int:
        return len(self.frame)

    def __bool__(self) -> bool:
        return len(self.frame) > 0

    def __getitem__(self, key):
        if isinstance(key, slice):
            idx = range(len(self))[key]
            return [dict(zip(self._columns, (c[i] for c in self._cols))) for i in idx]
        i = range(len(self))[key]
        return dict(zip(self._columns, (c[i] for c in self._cols)))

    def __iter__(self) -> Iterator[Dict[str, Any]]:
        for row in self.rows():
            yield dict(zip(self._columns, row))

    # --- accès rapide pour les connecteurs compatibles ---
    @property
    def columns(self) -> List[Any]:
        return list(self._columns)

    def rows(self) -> Iterator[Tuple[Any, ...]]:
        """Tuples de valeurs dans l'ordre des colonnes (pas de dict par ligne)."""
        return zip(*self._cols)
