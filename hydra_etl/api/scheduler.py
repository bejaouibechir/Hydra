"""
api/scheduler.py — Déclenchement automatique des workflows (trigger `schedule`).

Un unique BackgroundScheduler (APScheduler) tourne dans le process FastAPI.
Au démarrage, `start()` scanne tous les projets/workflows et enregistre un job
cron pour chaque workflow dont `trigger.type == "schedule"` avec un `cron` valide.

Chaque déclenchement réutilise EXACTEMENT le chemin d'exécution des runs manuels
(`api.routers.runs._execute_workflow`) : un run_id est créé, un run "pending" est
sauvé dans le store, puis le runner s'exécute. Aucune logique d'exécution dupliquée.

Source de vérité du trigger : le FICHIER YAML du workflow (comme le runner), avec
repli sur la métadonnée du store. Ça évite qu'un YAML édité à la main / importé
(trigger schedule) soit ignoré parce que la métadonnée dit encore "manual".

Synchronisation : les routes workflows (create/update/publish/delete) appellent
`sync_workflow(...)` ou `sync_all()` pour tenir le scheduler à jour sans redémarrage.

Dépendance : APScheduler>=3.10 (voir requirements.txt). Si APScheduler est absent,
le module se dégrade silencieusement (aucun crash de l'API) — le déclenchement
manuel reste disponible.
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Optional

from hydra_etl.api import store
from hydra_etl.api.models import RunResponse

logger = logging.getLogger("hydra.scheduler")

# Préfixe des ids de job APScheduler → 1 job cron par workflow.
_JOB_PREFIX = "wf:"

# Instance unique — None tant que start() n'a pas réussi (ou APScheduler absent).
_scheduler = None


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _job_id(workflow_id: str) -> str:
    return f"{_JOB_PREFIX}{workflow_id}"


def _trigger_from_file(path: Optional[str]):
    """Lit (type, cron) du trigger directement dans le fichier YAML du workflow.

    Même source de vérité que le runner (qui exécute le YAML). La métadonnée du
    store peut diverger si le YAML a été édité à la main / importé ; on privilégie
    donc le fichier. Retourne (None, None) si illisible → repli sur la métadonnée.
    """
    if not path:
        return None, None
    try:
        import yaml
        p = Path(path)
        if not p.exists():
            return None, None
        doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        wf = doc.get("workflow", {}) if isinstance(doc, dict) else {}
        trig = wf.get("trigger", {}) if isinstance(wf, dict) else {}
        if not isinstance(trig, dict):
            return None, None
        return trig.get("type"), trig.get("cron")
    except Exception:
        return None, None


# ---------------------------------------------------------------------------
# Exécution d'un workflow planifié — réutilise le chemin des runs manuels
# ---------------------------------------------------------------------------

def _run_scheduled_workflow(workflow_path: str, workflow_name: str, env: Optional[str]) -> None:
    """Callback APScheduler : lance un run comme le ferait POST /api/runs."""
    from hydra_etl.api.routers.runs import _execute_workflow

    wf_path = Path(workflow_path)
    if not wf_path.exists():
        logger.warning("Workflow planifié introuvable, job ignoré : %s", workflow_path)
        return

    run_id = str(uuid.uuid4())[:8]
    run = RunResponse(
        run_id=run_id,
        workflow_name=workflow_name,
        workflow_path=str(wf_path.resolve()),
        status="pending",
        started_at=_now(),
        trigger="schedule",
    )
    store.save_run(run)
    logger.info("Déclenchement planifié '%s' (run %s)", workflow_name, run_id)
    _execute_workflow(run_id, str(wf_path), None, env)


# ---------------------------------------------------------------------------
# Cycle de vie
# ---------------------------------------------------------------------------

def start() -> None:
    """Démarre le scheduler et enregistre tous les workflows planifiés."""
    global _scheduler
    if _scheduler is not None:
        return
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        logger.warning(
            "APScheduler non installé — les triggers 'schedule' sont inactifs. "
            "Installez-le : pip install APScheduler"
        )
        return

    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.start()
    logger.info("Scheduler démarré")
    sync_all()


def shutdown() -> None:
    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
        except Exception:
            pass
        _scheduler = None


# ---------------------------------------------------------------------------
# Synchronisation store ↔ scheduler
# ---------------------------------------------------------------------------

def _register(wf) -> bool:
    """(Ré)enregistre le job cron d'un workflow. Retourne True si planifié."""
    if _scheduler is None:
        return False
    try:
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        return False

    jid = _job_id(wf.id)
    # Retire l'ancien job (trigger passé de schedule à manual, ou cron modifié)
    if _scheduler.get_job(jid):
        _scheduler.remove_job(jid)

    # Source de vérité = le fichier YAML (comme le runner) ; repli sur la métadonnée.
    trig_type, cron = _trigger_from_file(wf.path)
    if trig_type is None:
        trig_type, cron = (wf.trigger_type or "manual"), wf.cron

    if trig_type != "schedule" or not cron:
        return False
    if not wf.path or not Path(wf.path).exists():
        logger.warning("Workflow '%s' planifié mais fichier absent : %s", wf.name, wf.path)
        return False

    try:
        trigger = CronTrigger.from_crontab(str(cron))
    except Exception as exc:
        logger.warning("Cron invalide pour '%s' (%s) : %s", wf.name, cron, exc)
        return False

    _scheduler.add_job(
        _run_scheduled_workflow,
        trigger=trigger,
        id=jid,
        args=[wf.path, wf.name, None],
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
    )
    logger.info("Planifié : '%s' → %s", wf.name, cron)
    return True


def sync_workflow(project_id: str, workflow_id: str) -> None:
    """Met à jour le job d'un seul workflow (après create/update/publish)."""
    if _scheduler is None:
        return
    wf = store.get_workflow(project_id, workflow_id)
    if wf is None:
        remove_workflow(workflow_id)
        return
    _register(wf)


def remove_workflow(workflow_id: str) -> None:
    """Retire le job d'un workflow (après delete)."""
    if _scheduler is None:
        return
    jid = _job_id(workflow_id)
    if _scheduler.get_job(jid):
        _scheduler.remove_job(jid)
        logger.info("Job planifié retiré : %s", workflow_id)


def sync_all() -> int:
    """Rescane tous les projets et réaligne le scheduler. Retourne le nb planifié."""
    if _scheduler is None:
        return 0
    for job in list(_scheduler.get_jobs()):
        if job.id.startswith(_JOB_PREFIX):
            _scheduler.remove_job(job.id)

    count = 0
    for proj in store.list_projects():
        for wf in store.list_workflows(proj.id):
            if _register(wf):
                count += 1
    logger.info("Scheduler synchronisé : %d workflow(s) planifié(s)", count)
    return count


def list_scheduled() -> list:
    """Liste des jobs planifiés actifs (pour debug/monitoring)."""
    if _scheduler is None:
        return []
    out = []
    for job in _scheduler.get_jobs():
        if job.id.startswith(_JOB_PREFIX):
            out.append({
                "workflow_id": job.id[len(_JOB_PREFIX):],
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            })
    return out
