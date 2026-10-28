"""
workflow/stop.py — Arrêt coopératif d'un workflow en cours (timeout du thread).

Python ne sait pas tuer un thread : le workflow est prié de s'arrêter et le fait
au prochain point de contrôle — entre deux groupes de steps, avant un step,
entre deux lots d'un job (lecture ou chargement) et juste avant la publication.
Un chargement en tout ou rien est alors annulé (`session.abort()`), une action
déjà lancée (bash, python, ssh…) va à son terme : elle a son propre `timeout`.
"""
from __future__ import annotations

import threading
from typing import Optional


class RunStopped(Exception):
    """Levée à un point de contrôle quand l'arrêt a été demandé."""


class StopSignal:
    """Demande d'arrêt partagée entre le lanceur (ProjectRunner) et le run."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self.reason: Optional[str] = None

    def stop(self, reason: str) -> None:
        if not self._event.is_set():
            self.reason = reason
            self._event.set()

    def is_set(self) -> bool:
        return self._event.is_set()

    def check(self) -> None:
        if self._event.is_set():
            raise RunStopped(self.reason or "stopped")


def check(stop: Optional[StopSignal]) -> None:
    """Point de contrôle : ne fait rien sans signal ou tant qu'il n'est pas levé."""
    if stop is not None:
        stop.check()
