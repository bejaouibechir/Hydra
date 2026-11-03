"""Déclencheurs de projet dans `hdrctl serve` : le même moteur que `hdrctl watch`.

Le moteur suit tous les projets de la liste Studio (ouverts, non retirés) ;
`sync()` est rappelé quand un projet est ouvert, retiré ou supprimé. Les
modifications de triggers.yaml sont relues par le moteur lui-même.
Environnement : `env:` du déclencheur, sinon HYDRA_ENV au lancement de serve.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from hydra_etl.triggers.engine import TriggerEngine

log = logging.getLogger("hydra.triggers.serve")
_engine: Optional[TriggerEngine] = None


def _log_event(e: dict) -> None:
    k = e.get("kind")
    who = f"{e.get('project')}/{e.get('trigger')}"
    if k == "started":
        log.info("trigger %s started (%s)", who, e.get("detail") or e.get("when"))
    elif k == "finished":
        log.info("trigger %s %s%s", who, e.get("status"), f": {e['error']}" if e.get("error") else "")
    elif k in ("error", "skipped"):
        log.warning("trigger %s: %s", who if e.get("trigger") else e.get("project"), e.get("error"))


def engine() -> Optional[TriggerEngine]:
    return _engine


def start() -> None:
    global _engine
    if _engine is not None:
        return
    _engine = TriggerEngine(env=os.environ.get("HYDRA_ENV") or None, origin="serve", on_event=_log_event)
    sync()
    _engine.start()
    log.info("trigger engine started")


def sync() -> None:
    """Aligne les projets suivis sur la liste du workspace Studio."""
    if _engine is None:
        return
    from hydra_etl.api import store
    wanted = set()
    for p in store.list_projects():
        root = Path(p.path)
        if (root / ".hydra").is_dir():
            wanted.add(root.resolve())
    for root in list(_engine.projects):
        if root not in wanted:
            _engine.remove_project(root)
    for root in wanted:
        if root not in _engine.projects:
            try:
                _engine.add_project(root)
            except Exception:  # noqa: BLE001 — un projet illisible ne bloque pas les autres
                log.exception("triggers of %s not loaded", root)


def shutdown(wait: float = 10.0) -> None:
    """Arrêt de serve : plus de lancement ; attend un peu les runs en cours."""
    global _engine
    if _engine is not None:
        _engine.stop(wait=wait)
        _engine = None
