"""
profiler.py — profil d'exécution d'un job (temps par étape).

Pourquoi
--------
Les plus gros écarts de performance mesurés sur Hydra viennent de la
configuration du job (batch_size trop petit, colonnes inutiles lues,
transformation coûteuse en tête de pipeline), pas du moteur. Rendre le
goulot visible permet de le corriger là où il est.

Usage
-----
    hydra run mon_job --profile
    HYDRA_PROFILE=1 hydra run mon_job

Le profil n'est calculé que s'il est demandé : désactivé, `span()` et
`iterate()` ne font qu'un `yield`, et `add()` retourne immédiatement.
"""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterable, Iterator, List, Optional

_TRUE = {"1", "true", "yes", "on"}


def profile_enabled(explicit: Optional[bool] = None) -> bool:
    """Profil actif si demandé explicitement, sinon via HYDRA_PROFILE."""
    if explicit is not None:
        return bool(explicit)
    return os.environ.get("HYDRA_PROFILE", "0").strip().lower() in _TRUE


class JobProfiler:
    """Accumulateur de temps par étiquette, dans l'ordre de première apparition."""

    __slots__ = ("enabled", "_acc", "_counts", "_order")

    def __init__(self, enabled: bool = False) -> None:
        self.enabled = bool(enabled)
        self._acc: Dict[str, float] = {}
        self._counts: Dict[str, int] = {}
        self._order: List[str] = []

    # ---------------------------------------------------------------- mesures
    def add(self, label: str, seconds: float, count: int = 1) -> None:
        if not self.enabled:
            return
        if label not in self._acc:
            self._acc[label] = 0.0
            self._counts[label] = 0
            self._order.append(label)
        self._acc[label] += seconds
        self._counts[label] += count

    @contextmanager
    def span(self, label: str):
        """Chronomètre un bloc et cumule son temps sous `label`."""
        if not self.enabled:
            yield
            return
        t0 = time.perf_counter()
        try:
            yield
        finally:
            self.add(label, time.perf_counter() - t0)

    def iterate(self, label: str, iterable: Iterable[Any]) -> Iterator[Any]:
        """Itère en ne comptant que le temps passé à *produire* chaque élément
        (le temps du corps de boucle appartient aux étapes suivantes)."""
        if not self.enabled:
            yield from iterable
            return
        it = iter(iterable)
        while True:
            t0 = time.perf_counter()
            try:
                item = next(it)
            except StopIteration:
                self.add(label, time.perf_counter() - t0, count=0)
                return
            self.add(label, time.perf_counter() - t0)
            yield item

    # ---------------------------------------------------------------- rapport
    def to_dict(self, *, total: float, rows_in: int = 0, rows_out: int = 0,
                job_id: str = "") -> Dict[str, Any]:
        measured = sum(self._acc.values())
        entries = [
            {
                "label": label,
                "seconds": round(self._acc[label], 4),
                "calls": self._counts[label],
                "share": (self._acc[label] / total) if total > 0 else 0.0,
            }
            for label in self._order
        ]
        rest = max(0.0, total - measured)
        if entries and total > 0 and rest / total >= 0.005:
            entries.append(
                {"label": "(reste : lecture YAML, connexion, etc.)",
                 "seconds": round(rest, 4), "calls": 0, "share": rest / total}
            )
        return {
            "job_id": job_id,
            "total": round(total, 4),
            "rows_in": rows_in,
            "rows_out": rows_out,
            "entries": entries,
        }


def format_profile(profile: Dict[str, Any]) -> str:
    """Rend le profil sous forme de tableau texte (une ligne par étape)."""
    if not profile:
        return ""
    total = float(profile.get("total") or 0.0)
    entries = profile.get("entries") or []
    width = max([len(str(e["label"])) for e in entries] + [12])
    head = f"Profil — job '{profile.get('job_id', '')}' — {total:.3f} s"
    lines = [head, "-" * len(head)]
    for e in entries:
        bar = "#" * max(0, int(round(float(e["share"]) * 30)))
        lines.append(
            f"  {str(e['label']):<{width}}  {float(e['seconds']):>8.3f} s  "
            f"{float(e['share']) * 100:>5.1f} %  {bar}"
        )
    rows_in = int(profile.get("rows_in") or 0)
    rows_out = int(profile.get("rows_out") or 0)
    n_in = f"{rows_in:,}".replace(",", " ")
    n_out = f"{rows_out:,}".replace(",", " ")
    rate = ""
    if total > 0 and rows_in:
        rate = " — " + f"{rows_in / total:,.0f}".replace(",", " ") + " lignes/s"
    lines.append(f"  {n_in} lignes lues, {n_out} écrites{rate}")
    return "\n".join(lines)
