"""
workflow/rollback.py — Annuler un workflow qui échoue (`rollback: true`).

Pendant le run, chaque step fait est empilé :
- un job publié : son enregistrement d'annulation (connector/undo.py) ;
- une action avec `undo:` : l'action à lancer pour la défaire.
Si le workflow échoue, la pile est défaite du dernier au premier. Une
annulation qui échoue (ou refusée parce que la destination a changé depuis)
arrête tout : le reste est gardé dans le journal, à finir avec
`hdrctl workflow undo <workflow>`. Workflow réussi : sauvegardes supprimées.

Journal : `.hydra/undo/<workflow>.json` du projet, écrit après chaque step
empilé et supprimé à la fin (réussite, ou annulation complète). S'il existe
au lancement suivant, le run refuse de démarrer : un run précédent s'est
arrêté sans finir (arrêt brutal, annulation en échec).

`rollback_problems()` vérifie AVANT le run que tout est annulable : chaque
job (destination et mode ; base en append : `load.key` exigée) et chaque
action qui agit hors de Hydra (`undo:` exigé, ou `undo: none`).
"""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import yaml

# Destinations annulables : type → modes
UNDOABLE = {
    "csv": {"replace", "append"},
    "parquet": {"replace", "append"},
    **{t: {"replace", "append", "upsert"} for t in
       ("postgresql", "postgres", "mysql", "mariadb", "sqlserver", "mssql")},
}
DB_TYPES = {"postgresql", "postgres", "mysql", "mariadb", "sqlserver", "mssql"}


# ── Vérification avant le run ──────────────────────────────────────────────
def _yaml(path: Path) -> Dict[str, Any]:
    try:
        d = yaml.safe_load(path.read_text(encoding="utf-8-sig")) or {}
        return d if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001 — erreurs de YAML : signalées par la validation du job
        return {}


def job_destination(job_dir: Path) -> Optional[Dict[str, Any]]:
    """{type, mode, key, id} de la destination écrite par le job (pipeline.to)."""
    pipe = _yaml(job_dir / "pipeline.yaml")
    p = pipe.get("pipeline") if isinstance(pipe.get("pipeline"), dict) else \
        (pipe.get("job") or {}).get("pipeline") if isinstance(pipe.get("job"), dict) else None
    to = (p or {}).get("to")
    dests = _yaml(job_dir / "destinations.yaml").get("destinations") or {}
    d = dests.get(to) if isinstance(dests, dict) else None
    if not isinstance(d, dict):
        return None
    load = d.get("load") if isinstance(d.get("load"), dict) else {}
    return {"id": to, "type": str(d.get("type", "")).strip().lower(),
            "mode": str(load.get("mode", "append")).strip().lower(), "key": load.get("key")}


def rollback_problems(workflow: Any, base_dir: Path) -> List[str]:
    """Ce qui empêcherait d'annuler ce workflow (vide = tout est annulable)."""
    from hydra_etl.workflow.models import SIDE_EFFECT_ACTIONS
    out: List[str] = []
    if not getattr(workflow, "rollback", False):
        return out
    for step in workflow.steps:
        if not step.enabled:
            continue
        if step.type == "job":
            jd = Path(step.job)
            if not jd.is_absolute():
                jd = Path(base_dir) / jd
            dest = job_destination(jd.resolve())
            if dest is None:
                continue                      # destination introuvable : erreur du job lui-même
            modes = UNDOABLE.get(dest["type"])
            if not modes or dest["mode"] not in modes:
                out.append(f"step '{step.name}': a '{dest['mode']}' load into a {dest['type'] or '?'} "
                           f"destination cannot be undone (rollback: true)")
            elif dest["type"] in DB_TYPES and dest["mode"] == "append" and not dest["key"]:
                out.append(f"step '{step.name}': append into a database with rollback: true needs "
                           f"load.key in {step.job}/destinations.yaml (the columns that identify "
                           f"a row), to remove exactly the rows of this run")
        elif step.action in SIDE_EFFECT_ACTIONS and step.undo is None:
            out.append(f"step '{step.name}': the '{step.action}' action acts outside Hydra; with "
                       f"rollback: true add undo: (the action that reverses it) or undo: none "
                       f"(nothing to reverse)")
    return out


# ── Journal ────────────────────────────────────────────────────────────────
def journal_path(project_root: Path, workflow_name: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", workflow_name) or "workflow"
    return Path(project_root) / ".hydra" / "undo" / f"{safe}.json"


class UndoStack:
    """Steps faits, dans l'ordre, et leur journal sur disque."""

    def __init__(self, journal: Path, workflow_name: str) -> None:
        self.journal = journal
        self.workflow_name = workflow_name
        self.entries: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    @classmethod
    def load(cls, journal: Path) -> "UndoStack":
        data = json.loads(journal.read_text(encoding="utf-8"))
        st = cls(journal, data.get("workflow", ""))
        st.entries = list(data.get("entries", []))
        return st

    def push_job(self, step: str, record: Any, connector: Any = None) -> None:
        with self._lock:
            self.entries.append({"step": step, "type": "job", "record": record.to_dict(),
                                 "_record": record, "_connector": connector})
            self._save()

    def push_action(self, step: str, undo: Any) -> None:
        with self._lock:
            spec = undo.model_dump() if hasattr(undo, "model_dump") else dict(undo)
            self.entries.append({"step": step, "type": "action", "undo": spec})
            self._save()

    def _save(self) -> None:
        if not self.entries:
            self.remove()
            return
        self.journal.parent.mkdir(parents=True, exist_ok=True)
        clean = [{k: v for k, v in e.items() if not k.startswith("_")} for e in self.entries]
        from hydra_etl.internal.fs_atomic import atomic_write_text
        atomic_write_text(self.journal, json.dumps(
            {"workflow": self.workflow_name, "entries": clean}, indent=2, default=str))

    def remove(self) -> None:
        try:
            self.journal.unlink()
        except FileNotFoundError:
            pass

    # ── fin du run ──
    def discard_all(self, connector_for: Callable[[Dict[str, Any]], Any]) -> List[str]:
        """Workflow réussi : supprimer les sauvegardes. Rend les avertissements."""
        from hydra_etl.internal.connector.undo import undo_from_dict
        warnings = []
        for e in self.entries:
            if e["type"] != "job":
                continue
            rec = e.get("_record") or undo_from_dict(e["record"])
            try:
                rec.discard(e.get("_connector") or (connector_for(e) if rec.kind == "db" else None))
            except Exception as ex:  # noqa: BLE001 — la donnée est bonne, seule une copie reste
                warnings.append(f"could not remove the backup of '{e['step']}': {ex}")
        self.entries = []
        self.remove()
        return warnings

    def undo_all(self, run_action: Callable[[str, Dict[str, Any]], Tuple[bool, str]],
                 connector_for: Callable[[Dict[str, Any]], Any]) -> Dict[str, Any]:
        """Défait la pile, du dernier step au premier. S'arrête au premier échec."""
        from hydra_etl.internal.connector.undo import undo_from_dict
        report: List[Dict[str, Any]] = []
        status = "nothing" if not self.entries else "done"
        while self.entries:
            e = self.entries[-1]
            try:
                if e["type"] == "job":
                    rec = e.get("_record") or undo_from_dict(e["record"])
                    conn = e.get("_connector") or (connector_for(e) if rec.kind == "db" else None)
                    msg = rec.undo(conn)
                else:
                    ok, msg = run_action(e["step"], e["undo"])
                    if not ok:
                        raise RuntimeError(msg)
            except Exception as ex:  # noqa: BLE001
                report.append({"step": e["step"], "status": "failed", "message": str(ex)})
                status = "failed"
                break
            report.append({"step": e["step"], "status": "undone", "message": msg})
            self.entries.pop()
            self._save()
        if status != "failed":
            self.remove()
        return {"status": status, "steps": report,
                "journal": str(self.journal) if status == "failed" else None}


def connector_from_entry(entry: Dict[str, Any], *, root: Path, env: Optional[str] = None,
                         params: Optional[Dict[str, Any]] = None) -> Any:
    """Connecteur de destination reconstruit comme à l'exécution (journal)."""
    from hydra_etl.internal.runner.executor import JobExecutor
    rec = entry["record"]
    ex = JobExecutor(job_dir=Path(rec["job_dir"]), root_dir=Path(root), env=env, params=dict(params or {}))
    cfg = ex._dest_parser.parse(ex._load_yaml_with_resolution(ex._destinations_file, required=True))
    d = ex._get_dest_def(cfg, rec["dest_id"])
    return ex._build_connector(rec["dest_id"], d, is_source=False)
