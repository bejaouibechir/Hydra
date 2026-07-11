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

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Manifest models (lecture du YAML)
# ---------------------------------------------------------------------------

class Trigger(BaseModel):
    """Déclencheur du workflow."""
    type: Literal["manual", "schedule", "webhook"] = "manual"
    cron: Optional[str] = None

    @model_validator(mode="after")
    def _validate_cron(self) -> "Trigger":
        if self.type == "schedule" and not self.cron:
            raise ValueError("trigger.cron est requis quand type='schedule'")
        return self


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

    @model_validator(mode="after")
    def _validate_fields(self) -> "WorkflowStep":
        if self.type == "job" and not self.job:
            raise ValueError(f"Step '{self.name}': type=job requiert le champ 'job'")
        if self.type == "action" and not self.action:
            raise ValueError(f"Step '{self.name}': type=action requiert le champ 'action'")
        return self


class WorkflowDef(BaseModel):
    """Définition complète d'un workflow — issu de workflow.yaml."""
    version: str = "1.0"
    name: str
    description: Optional[str] = None
    trigger: Trigger = Field(default_factory=Trigger)
    steps: List[WorkflowStep]

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
