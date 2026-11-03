"""api/routers/triggers.py — déclencheurs de projet (triggers.yaml) dans hdrctl serve.

    GET  /api/projects/{id}/triggers                     liste, prochaine échéance, dernier run
    PUT  /api/projects/{id}/triggers                     enregistre triggers.yaml (Studio)
    POST /api/projects/{id}/triggers/{name}/token        crée / remplace le jeton d'un webhook
    GET  /api/projects/{id}/triggers/history             historique (?name=&limit=)
    POST /api/projects/{id}/triggers/{name}/fire         lancer maintenant (Studio, API)
    POST /api/projects/{id}/triggers/{name}/webhook      appel externe, avec le jeton du déclencheur

Le webhook est la seule route pensée pour un appelant extérieur : elle exige le
jeton (`X-Hydra-Token: <jeton>` ou `Authorization: Bearer <jeton>`), comparé en
temps constant au secret désigné par `token:`. Aucune donnée de la requête
n'est transmise au projet.
"""
from __future__ import annotations

import hmac
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from hydra_etl.api import store

router = APIRouter()


def _root(project_id: str) -> Path:
    proj = store.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    return Path(proj.path).resolve()


def _engine():
    from hydra_etl.api import trigger_service
    eng = trigger_service.engine()
    if eng is None:                      # serve sans lifespan (tests) : démarrage à la demande
        trigger_service.start()
        eng = trigger_service.engine()
    return eng


def _load(root: Path):
    from hydra_etl.triggers.models import TriggerFileError, load_triggers
    try:
        return load_triggers(root)
    except TriggerFileError as e:
        raise HTTPException(status_code=422, detail={"message": "invalid triggers.yaml", "errors": e.errors})


@router.get("/{project_id}/triggers")
def list_triggers(project_id: str) -> Dict[str, Any]:
    from hydra_etl.triggers.core import check_triggers, last_runs
    from hydra_etl.triggers.models import TriggerFileError, load_triggers
    root = _root(project_id)
    try:
        tf = load_triggers(root)
    except TriggerFileError as e:
        return {"file": str(root / "triggers.yaml"), "exists": True, "triggers": [],
                "errors": e.errors, "warnings": [], "invalid": True, **_choices(root)}
    check = check_triggers(root, tf)
    eng = _engine()
    st = eng.projects.get(root) or eng.add_project(root)
    status = {w.trigger.name: eng.describe(st, w) for w in st.watched.values()}
    from hydra_etl.triggers.core import token_is_set
    from hydra_etl.triggers.models import trigger_to_dict
    last = last_runs(root)
    out: List[Dict[str, Any]] = []
    for t in tf.triggers:
        s = status.get(t.name, {})
        nxt = s.get("next")
        out.append({
            "name": t.name, "type": t.type, "enabled": t.enabled, "when": t.when(),
            "description": t.description, "env": t.env, "workflows": t.workflows,
            "next": nxt.isoformat() if nxt else None, "running": bool(s.get("running")),
            "note": s.get("note"), "last": last.get(t.name),
            "webhook": f"/api/projects/{project_id}/triggers/{t.name}/webhook" if t.type == "webhook" else None,
            "token_set": token_is_set(root, t) if t.type == "webhook" else None,
            "config": trigger_to_dict(t),
        })
    return {"file": str(root / "triggers.yaml"), "exists": (root / "triggers.yaml").is_file(),
            "triggers": out, "errors": check.errors, "warnings": check.warnings, **_choices(root)}


def _choices(root: Path) -> Dict[str, Any]:
    """Ce que le formulaire Studio propose : workflows du projet, sources de ses jobs."""
    from hydra_etl.triggers.core import _source_ids
    from hydra_etl.workflow.project import workflow_files
    sources = []
    for d in sorted((root / "jobs").glob("*")) if (root / "jobs").is_dir() else []:
        if (d / "sources.yaml").is_file():
            sources.append({"job": f"jobs/{d.name}", "ids": _source_ids(d)})
    return {"workflows": list(workflow_files(root)), "sources": sources}


@router.get("/{project_id}/triggers/history")
def trigger_history(project_id: str, name: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    from hydra_etl.triggers.core import read_history
    return read_history(_root(project_id), name, max(1, min(limit, 1000)))


def _fire(project_id: str, name: str, origin: str) -> Dict[str, Any]:
    root = _root(project_id)
    try:
        _engine().fire_now(root, name, origin=origin)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"trigger": name, "status": "started", "origin": origin}


@router.post("/{project_id}/triggers/{name}/fire", status_code=202)
def fire_trigger(project_id: str, name: str) -> Dict[str, Any]:
    """Lance le projet maintenant, comme le déclencheur `name` (tous types)."""
    return _fire(project_id, name, "api")


def _token_from(x_hydra_token: Optional[str], authorization: Optional[str]) -> Optional[str]:
    if x_hydra_token:
        return x_hydra_token.strip()
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


@router.post("/{project_id}/triggers/{name}/webhook", status_code=202)
def webhook(project_id: str, name: str,
            x_hydra_token: Optional[str] = Header(default=None),
            authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    """Appel externe : lance le projet si le jeton est le bon."""
    from hydra_etl.internal.config.secrets import SecretResolutionError, SecretResolver, project_secrets
    root = _root(project_id)
    t = _load(root).get(name)
    # Même réponse pour un déclencheur inconnu ou d'un autre type : rien à deviner.
    if t is None or t.type != "webhook" or not t.enabled:
        raise HTTPException(status_code=404, detail=f"no webhook trigger '{name}'")
    given = _token_from(x_hydra_token, authorization)
    if not given:
        raise HTTPException(status_code=401, detail="token required (X-Hydra-Token or Authorization: Bearer)")
    secret_name = str(t.token).strip()[len("${SECRET:"):-1]
    import os
    env = t.env or os.environ.get("HYDRA_ENV") or None
    try:
        expected = SecretResolver(secrets={}, fallback=project_secrets(root, env=env))._get_secret(secret_name)
    except SecretResolutionError:
        raise HTTPException(status_code=503,
                            detail=f"the token of trigger '{name}' is not set (hdrctl trigger token {name})")
    if not hmac.compare_digest(given.encode(), str(expected).encode()):
        raise HTTPException(status_code=401, detail="invalid token")
    return _fire(project_id, name, "webhook")


class TriggersBody(BaseModel):
    triggers: List[Dict[str, Any]]


@router.put("/{project_id}/triggers")
def save_triggers(project_id: str, body: TriggersBody) -> Dict[str, Any]:
    """Remplace triggers.yaml (Studio). Refusé (422) si un déclencheur est invalide ou si
    `hdrctl trigger validate` échouerait ; l'ancien fichier est copié dans ~/.hydra/_backups.
    Les commentaires du fichier ne sont pas conservés."""
    from pydantic import ValidationError
    from hydra_etl.triggers.core import check_triggers
    from hydra_etl.triggers.models import TriggerFile, _messages, save_triggers as _save
    root = _root(project_id)
    items = []
    for raw in body.triggers:                     # un booléen YAML 1.1 venu d'un client
        d = dict(raw)
        if True in d and "on" not in d:
            d["on"] = d.pop(True)
        items.append(d)
    try:
        tf = TriggerFile(triggers=items)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail={"message": "invalid triggers", "errors": _messages(e)})
    check = check_triggers(root, tf)
    if check.errors:
        raise HTTPException(status_code=422, detail={"message": "triggers refused", "errors": check.errors})
    _save(root, tf)
    try:
        from hydra_etl.api import trigger_service
        trigger_service.sync()                    # le moteur relit le fichier de lui-même
    except Exception:  # noqa: BLE001
        pass
    return list_triggers(project_id)


class TokenBody(BaseModel):
    env: Optional[str] = None
    rotate: bool = False


@router.post("/{project_id}/triggers/{name}/token")
def create_token(project_id: str, name: str, body: TokenBody) -> Dict[str, Any]:
    """Crée le jeton d'un déclencheur webhook (secret du projet). La valeur n'est rendue
    qu'ici, une seule fois ; 409 si un jeton existe déjà (rotate: true pour le remplacer)."""
    from hydra_etl.internal.config.env_admin import EnvAdminError
    from hydra_etl.triggers.core import TokenExists, create_token as _create
    root = _root(project_id)
    t = _load(root).get(name)
    if t is None or t.type != "webhook":
        raise HTTPException(status_code=404, detail=f"no webhook trigger '{name}'")
    try:
        value, secret, path = _create(root, t, env=body.env or None, rotate=body.rotate)
    except TokenExists as e:
        raise HTTPException(status_code=409, detail=str(e))
    except (EnvAdminError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"trigger": name, "token": value, "secret": secret, "file": str(path),
            "url": f"/api/projects/{project_id}/triggers/{name}/webhook", "header": "X-Hydra-Token"}
