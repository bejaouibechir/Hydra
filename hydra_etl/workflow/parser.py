"""
workflow/parser.py — Lecture et validation d'un workflow.yaml.

Usage:
    from hydra_etl.workflow.parser import load_workflow
    wf = load_workflow("./my_workflow.yaml")
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Union

import yaml
from pydantic import ValidationError

from hydra_etl.workflow.models import WorkflowDef


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

    # Regle 3.2 : lecture tolerante de la version du DSL.
    from hydra_etl.internal.dsl_version import check_dsl_version
    check_dsl_version(raw, path.name)

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
    except ValidationError as e:
        # Une ligne par erreur, sans le bruit Pydantic (type=, input_value=, URL).
        lines = []
        for err in e.errors():
            msg = str(err.get("msg", "")).replace("Value error, ", "", 1)
            loc = ".".join(str(x) for x in err.get("loc", ()))
            lines.append(f"  - {loc}: {msg}" if loc else f"  - {msg}")
        raise ValueError(
            f"Workflow validation error in '{path}':\n" + "\n".join(lines)
        ) from e
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
        from hydra_etl.workflow.runner import WorkflowRunner
        runner = WorkflowRunner(wf)
        runner._build_execution_groups()  # lève ValueError si cycle
        return True, ""
    except Exception as e:
        return False, str(e)
