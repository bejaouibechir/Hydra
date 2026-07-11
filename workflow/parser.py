"""
workflow/parser.py — Lecture et validation d'un workflow.yaml.

Usage:
    from workflow.parser import load_workflow
    wf = load_workflow("./my_workflow.yaml")
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Union

import yaml

from workflow.models import WorkflowDef


def load_workflow(path: Union[str, Path]) -> WorkflowDef:
    """
    Charge un fichier workflow.yaml et retourne un WorkflowDef validé.

    Le YAML doit avoir la structure :
        workflow:
          name: ...
          steps: [...]

    Raises:
        FileNotFoundError : fichier introuvable
        ValueError        : YAML invalide ou validation Pydantic échouée
    """
    path = Path(path).resolve()

    if not path.exists():
        raise FileNotFoundError(f"Workflow file not found: {path}")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ValueError(f"YAML parse error in '{path}': {e}") from e

    if not isinstance(raw, dict):
        raise ValueError(f"Invalid workflow YAML: expected mapping, got {type(raw).__name__}")

    wf_data = raw.get("workflow")
    if wf_data is None:
        raise ValueError(
            f"'{path}' must have a top-level 'workflow' key.\n"
            f"Expected:\n  workflow:\n    name: ...\n    steps: [...]"
        )

    if not isinstance(wf_data, dict):
        raise ValueError(f"'workflow' must be a mapping, got {type(wf_data).__name__}")

    try:
        return WorkflowDef(**wf_data)
    except Exception as e:
        raise ValueError(f"Workflow validation error in '{path}': {e}") from e


def validate_workflow(path: Union[str, Path]) -> tuple[bool, str]:
    """
    Valide un workflow.yaml sans l'exécuter.

    Returns:
        (True, "")            si valide
        (False, error_msg)    si invalide
    """
    try:
        wf = load_workflow(path)
        # Vérification supplémentaire : cycles
        from workflow.runner import WorkflowRunner
        runner = WorkflowRunner(wf)
        runner._build_execution_groups()  # lève ValueError si cycle
        return True, ""
    except Exception as e:
        return False, str(e)
