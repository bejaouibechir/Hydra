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

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

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
            raise ValueError("trigger.cron est requis quand type='schedule'")
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


class WorkflowStep(BaseModel):
    """Un step du workflow — soit un job Hydra, soit une action."""
    name: str
    type: Literal["job", "action"]

    # type=job
    job: Optional[str] = None          # chemin vers le dossier job

    # type=action
    action: Optional[str] = None       # webhook | log | slack | email ...
    params: Optional[Dict[str, Any]] = None

    # Orchestration
    depends_on: List[str] = Field(default_factory=list)
    on_failure: Literal["fail", "skip", "continue"] = "fail"
    enabled: bool = True    # False → step ignoré à l'exécution
    retry: Optional[RetryPolicy] = None   # re-tentatives (via Retry-scope)
    when: Optional[str] = None            # garde conditionnelle : step exécuté seulement si l'expression est vraie

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _no_unknown_keys(cls, data: Any) -> Any:
        name = data.get("name", "?") if isinstance(data, dict) else "?"
        _reject_unknown_keys(data, cls.model_fields, f"Step '{name}'")
        return data

    @model_validator(mode="after")
    def _validate_fields(self) -> "WorkflowStep":
        if self.type == "job" and not self.job:
            raise ValueError(f"Step '{self.name}': type=job requiert le champ 'job'")
        if self.type == "action" and not self.action:
            raise ValueError(f"Step '{self.name}': type=action requiert le champ 'action'")
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
        return self


class WorkflowDef(BaseModel):
    """Définition complète d'un workflow — issu de workflow.yaml."""
    version: str = "1.0"
    name: str
    description: Optional[str] = None
    trigger: Trigger = Field(default_factory=Trigger)
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
            raise ValueError(f"Noms de steps dupliqués : {duplicates}")
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
            "steps": [
                {
                    "step_name": s.step_name,
                    "success": s.success,
                    "duration": s.duration,
                    "error": s.error,
                    "logs": s.logs,
                    "skipped": s.skipped,
                    "rows_in":  s.job_result.rows_in  if s.job_result else None,
                    "rows_out": s.job_result.rows_out if s.job_result else None,
                    "output_sample":  s.job_result.output_sample  if s.job_result else None,
                    "output_columns": s.job_result.output_columns if s.job_result else None,
                }
                for s in self.steps
            ],
        }
