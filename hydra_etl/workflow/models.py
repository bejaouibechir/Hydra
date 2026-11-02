"""
workflow/models.py — Modèles Pydantic pour le Workflow Engine.

Hiérarchie :
    WorkflowDef
      └── trigger : Trigger
      └── steps   : List[WorkflowStep]

Résultats d'exécution :
    WorkflowResult
      └── steps : List[StepResult]
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator


# Paramètres de chaque action : (requis, facultatifs). Source de vérité de la
# validation — une action absente est refusée, un paramètre absent de ses deux
# listes aussi, un paramètre requis manquant ou vide aussi. Tout est vérifié au
# chargement : `workflow validate` échoue, `workflow run` ne démarre pas.
#
# Doit rester aligné sur :
#   - les clés de `action_handlers` dans workflow/runner.py ;
#   - les `params.get(...)` de chaque handler ;
#   - les champs proposés par Studio (NodeConfigDialog.tsx).
# Des tests de parité dans tests/test_workflow.py vérifient les deux premiers
# et le troisième.
ACTION_PARAMS: Dict[str, "tuple[frozenset, frozenset]"] = {
    "log":          (frozenset(), frozenset({"message"})),
    "delay":        (frozenset(), frozenset({"seconds", "duration"})),
    "webhook":      (frozenset({"url"}), frozenset({"method", "body", "headers"})),
    "email":        (frozenset({"to"}), frozenset({
                        "subject", "body", "from_addr", "smtp_host", "smtp_port",
                        "username", "password", "use_tls"})),
    "bash":         (frozenset({"command"}), frozenset({"working_dir", "timeout"})),
    "powershell":   (frozenset({"command"}), frozenset({"working_dir", "timeout"})),
    "ssh":          (frozenset({"host", "username", "command"}),
                     frozenset({"port", "password", "key_path", "timeout"})),
    "python":       (frozenset(), frozenset({"script", "file_path", "working_dir", "timeout"})),
    "set_param":    (frozenset({"name", "value"}), frozenset({"type"})),
    "assign_param": (frozenset({"name", "value"}), frozenset({"type"})),
    "condition":    (frozenset(), frozenset({"mode", "expr", "left", "op", "right", "name"})),
}

WORKFLOW_ACTIONS = frozenset(ACTION_PARAMS)

# Actions qui agissent hors de Hydra : avec `rollback: true`, chacune déclare
# comment la défaire (`undo:` une action, ou `undo: none`). Les autres (log,
# delay, condition, set_param, assign_param) n'ont rien à défaire.
SIDE_EFFECT_ACTIONS = frozenset({"webhook", "email", "bash", "powershell", "ssh", "python"})


def _suggest(word: str, candidates) -> str:
    import difflib
    close = difflib.get_close_matches(str(word).lower(), list(candidates), n=1, cutoff=0.6)
    return f" — did you mean '{close[0]}'?" if close else ""


def _unknown_action_message(step_name: str, action: str) -> str:
    return (f"Step '{step_name}': unknown action '{action}'. "
            f"Valid actions: {', '.join(sorted(WORKFLOW_ACTIONS))}"
            + _suggest(action, WORKFLOW_ACTIONS))


def _reject_unknown_keys(data: Any, allowed, where: str) -> None:
    """Refuse toute clé inconnue, avec suggestion. Une clé mal orthographiée
    (`depend_on`) serait sinon ignorée en silence."""
    if not isinstance(data, dict):
        return
    for key in data:
        if key not in allowed:
            raise ValueError(
                f"{where}: unknown key '{key}'{_suggest(key, allowed)} "
                f"Valid keys: {', '.join(sorted(allowed))}"
            )


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _check_action_params(step_name: str, action: str, params: Optional[Dict[str, Any]]) -> None:
    required, optional = ACTION_PARAMS[action]
    params = params or {}
    allowed = required | optional
    for key in params:
        if key not in allowed:
            raise ValueError(
                f"Step '{step_name}': unknown parameter '{key}' for action "
                f"'{action}'{_suggest(key, allowed)} "
                f"Valid parameters: {', '.join(sorted(allowed)) or '(none)'}"
            )
    for key in sorted(required):
        if _is_blank(params.get(key)):
            raise ValueError(
                f"Step '{step_name}': action '{action}' requires parameter '{key}'"
            )
    if action == "python" and _is_blank(params.get("script")) and _is_blank(params.get("file_path")):
        raise ValueError(
            f"Step '{step_name}': action 'python' requires 'script' or 'file_path'"
        )


# ---------------------------------------------------------------------------
# Manifest models (lecture du YAML)
# ---------------------------------------------------------------------------

class Trigger(BaseModel):
    """Déclencheur du workflow."""
    model_config = ConfigDict(extra="forbid")
    type: Literal["manual", "schedule", "webhook"] = "manual"
    cron: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _no_unknown_keys(cls, data: Any) -> Any:
        _reject_unknown_keys(data, cls.model_fields, "trigger")
        return data

    @model_validator(mode="after")
    def _validate_cron(self) -> "Trigger":
        if self.type == "schedule" and not self.cron:
            raise ValueError("trigger.cron is required when type='schedule'")
        return self


class RetryPolicy(BaseModel):
    """Politique de re-tentative d'un step (appliquée par Retry-scope)."""
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _no_unknown_keys(cls, data: Any) -> Any:
        _reject_unknown_keys(data, cls.model_fields, "retry")
        return data

    max: int = 0                                      # re-tentatives APRÈS le 1er échec (0 = aucune)
    delay: float = 0.0                                # secondes d'attente entre tentatives
    backoff: Literal["fixed", "exponential"] = "fixed"


class UndoAction(BaseModel):
    """`undo:` d'un step action — l'action qui défait ce qu'il a fait, lancée
    si le workflow (en `rollback: true`) échoue après lui."""
    model_config = ConfigDict(extra="forbid")
    action: str
    params: Optional[Dict[str, Any]] = None

    @model_validator(mode="before")
    @classmethod
    def _no_unknown_keys(cls, data: Any) -> Any:
        _reject_unknown_keys(data, cls.model_fields, "undo")
        return data


_PROJECT_ENV_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_\-]*$")
_PROJECT_PARAM_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")
_PROJECT_VAR_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
# Champs propres à type=project (refusés sur les autres types)
PROJECT_STEP_FIELDS = ("project", "ref", "env", "variables", "workflows", "outputs", "isolation")


class WorkflowStep(BaseModel):
    """Un step du workflow — un job Hydra, une action, ou un autre projet
    (type=project : projet esclave lancé par ce workflow)."""
    name: str
    type: Literal["job", "action", "project"]

    # type=job
    job: Optional[str] = None          # chemin vers le dossier job

    # type=action
    action: Optional[str] = None       # webhook | log | slack | email ...
    params: Optional[Dict[str, Any]] = None   # action : ses paramètres ; project : paramètres passés à l'esclave

    # type=project — projet esclave (Hydra 0.19)
    project: Optional[str] = None      # chemin (ref: path, défaut) ou nom du workspace (ref: name)
    ref: Optional[Literal["path", "name"]] = None
    env: Optional[str] = None          # inherit (défaut) | none | <nom d'environnement>
    variables: Optional[Dict[str, Any]] = None   # variables d'environnement prêtées pour ce run
    workflows: Optional[List[str]] = None        # sinon : le thread.yaml de l'esclave
    outputs: Optional[List[str]] = None          # paramètres publiés par l'esclave, relus ici
    isolation: Optional[Literal["inprocess", "subprocess"]] = None   # défaut inprocess

    # Orchestration
    depends_on: List[str] = Field(default_factory=list)
    on_failure: Literal["fail", "skip", "continue"] = "fail"
    enabled: bool = True    # False → step ignoré à l'exécution
    retry: Optional[RetryPolicy] = None   # re-tentatives (via Retry-scope)
    when: Optional[str] = None            # garde conditionnelle : step exécuté seulement si l'expression est vraie
    # Action seulement : comment défaire ce step si le workflow (rollback: true)
    # échoue après lui — une action, ou "none" (rien à défaire / accepté).
    undo: Optional[Union[Literal["none"], UndoAction]] = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _no_unknown_keys(cls, data: Any) -> Any:
        name = data.get("name", "?") if isinstance(data, dict) else "?"
        _reject_unknown_keys(data, cls.model_fields, f"Step '{name}'")
        return data

    def _validate_project_step(self) -> None:
        n = self.name
        if not self.project or not str(self.project).strip():
            raise ValueError(f"Step '{n}': type=project requires the 'project' field "
                             f"(path of the project, or its name with ref: name)")
        for f in ("job", "action"):
            if getattr(self, f):
                raise ValueError(f"Step '{n}': '{f}' applies to type={f}, not type=project")
        if self.undo is not None:
            raise ValueError(f"Step '{n}': 'undo' applies to type=action, not type=project")
        if self.env is not None and self.env not in ("inherit", "none") \
                and not _PROJECT_ENV_RE.match(str(self.env)):
            raise ValueError(f"Step '{n}': env '{self.env}' — use inherit, none or an environment "
                             f"name (letters, digits, '_' or '-')")
        for k in (self.params or {}):
            if not _PROJECT_PARAM_RE.match(str(k)):
                raise ValueError(f"Step '{n}': params: invalid parameter name '{k}' "
                                 f"(letters, digits, '.', '_' or '-')")
        for k, v in (self.variables or {}).items():
            if not _PROJECT_VAR_RE.match(str(k)):
                raise ValueError(f"Step '{n}': variables: invalid variable name '{k}' "
                                 f"(letters, digits and '_', not starting with a digit)")
            if isinstance(v, (dict, list)):
                raise ValueError(f"Step '{n}': variables: '{k}' must be a single value")
            if isinstance(v, str) and "${SECRET:" in v:
                raise ValueError(f"Step '{n}': variables: '{k}' passes a secret; a project keeps "
                                 f"its own secrets (.hydra/secrets of the called project)")
        for k, v in (self.params or {}).items():
            if isinstance(v, str) and "${SECRET:" in v:
                raise ValueError(f"Step '{n}': params: '{k}' passes a secret; a project keeps "
                                 f"its own secrets (.hydra/secrets of the called project)")
        for label, names in (("workflows", self.workflows), ("outputs", self.outputs)):
            if names is not None and not names:
                raise ValueError(f"Step '{n}': {label} is empty — remove it or list names")
            for x in names or []:
                if not isinstance(x, str) or not _PROJECT_PARAM_RE.match(x):
                    raise ValueError(f"Step '{n}': {label}: invalid name '{x}'")

    @model_validator(mode="after")
    def _validate_fields(self) -> "WorkflowStep":
        if self.type == "job" and not self.job:
            raise ValueError(f"Step '{self.name}': type=job requires the 'job' field")
        if self.type == "action" and not self.action:
            raise ValueError(f"Step '{self.name}': type=action requires the 'action' field")
        if self.type == "project":
            self._validate_project_step()
            return self
        extra = [f for f in PROJECT_STEP_FIELDS if getattr(self, f) is not None]
        if extra:
            raise ValueError(f"Step '{self.name}': {', '.join(extra)} "
                             f"{'applies' if len(extra) == 1 else 'apply'} to type=project, "
                             f"not type={self.type}")
        # Un champ qui ne s'applique pas à ce type serait ignoré en silence.
        if self.type == "job" and (self.action or self.params):
            raise ValueError(
                f"Step '{self.name}': 'action' and 'params' apply to type=action, not type=job"
            )
        if self.type == "action" and self.job:
            raise ValueError(
                f"Step '{self.name}': 'job' applies to type=job, not type=action"
            )
        if self.type == "action":
            if self.action not in WORKFLOW_ACTIONS:
                raise ValueError(_unknown_action_message(self.name, self.action))
            _check_action_params(self.name, self.action, self.params)
        if self.undo is not None:
            if self.type == "job":
                raise ValueError(
                    f"Step '{self.name}': 'undo' applies to type=action; a job is undone "
                    f"automatically (rollback: true on the workflow)")
            if isinstance(self.undo, UndoAction):
                if self.undo.action not in WORKFLOW_ACTIONS:
                    raise ValueError(_unknown_action_message(f"{self.name} (undo)", self.undo.action))
                _check_action_params(f"{self.name} (undo)", self.undo.action, self.undo.params)
        return self


class WorkflowDef(BaseModel):
    """Définition complète d'un workflow — issu de workflow.yaml."""
    version: str = "1.0"
    name: str
    description: Optional[str] = None
    trigger: Trigger = Field(default_factory=Trigger)
    # Si le workflow échoue : défaire les steps déjà faits, du dernier au premier
    # (jobs : automatiquement ; actions : leur `undo:`). Voir workflow/rollback.py.
    rollback: bool = False
    steps: List[WorkflowStep]

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _no_unknown_keys(cls, data: Any) -> Any:
        _reject_unknown_keys(data, cls.model_fields, "workflow")
        return data

    @model_validator(mode="after")
    def _validate_unique_names(self) -> "WorkflowDef":
        names = [s.name for s in self.steps]
        duplicates = {n for n in names if names.count(n) > 1}
        if duplicates:
            raise ValueError(f"Duplicate step names: {duplicates}")
        return self


# ---------------------------------------------------------------------------
# Résultats d'exécution
# ---------------------------------------------------------------------------

@dataclass
class StepResult:
    """Résultat d'exécution d'un step individuel."""
    step_name: str
    success: bool
    duration: float
    error: Optional[str] = None
    job_result: Optional[Any] = None   # JobResult si type=job
    logs: List[str] = field(default_factory=list)   # lignes de log capturées
    output: List[str] = field(default_factory=list)  # stdout/stderr d'une action script
    skipped: bool = False
    undo_of: Optional[str] = None      # step d'annulation (rollback) : step qu'il défait

    def __str__(self) -> str:
        status = "⏭" if self.skipped else ("✅" if self.success else "❌")
        base = f"StepResult({status} {self.step_name} | {self.duration:.2f}s)"
        if self.error:
            base += f" error={self.error}"
        return base


@dataclass
class WorkflowResult:
    """Résultat d'exécution d'un workflow complet."""
    workflow_name: str
    success: bool
    duration: float
    steps: List[StepResult] = field(default_factory=list)
    error: Optional[str] = None
    # rollback: true et échec : {"status": done | failed | nothing,
    # "steps": [{"step", "status", "message"}], "journal": chemin ou None}
    rollback: Optional[Dict[str, Any]] = None

    def __str__(self) -> str:
        status = "✅ SUCCESS" if self.success else "❌ FAILED"
        n_ok = sum(1 for s in self.steps if s.success)
        return (
            f"WorkflowResult({status} | {self.workflow_name} | "
            f"{n_ok}/{len(self.steps)} steps OK | {self.duration:.2f}s)"
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflow_name": self.workflow_name,
            "success": self.success,
            "duration": self.duration,
            "error": self.error,
            "rollback": self.rollback,
            "steps": [
                {
                    "step_name": s.step_name,
                    "success": s.success,
                    "duration": s.duration,
                    "error": s.error,
                    "logs": s.logs,
                    "skipped": s.skipped,
                    "undo_of": s.undo_of,
                    "rows_in":  s.job_result.rows_in  if s.job_result else None,
                    "rows_out": s.job_result.rows_out if s.job_result else None,
                    "output_sample":  s.job_result.output_sample  if s.job_result else None,
                    "output_columns": s.job_result.output_columns if s.job_result else None,
                }
                for s in self.steps
            ],
        }
