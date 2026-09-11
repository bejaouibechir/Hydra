"""Valide le corpus statique d'exemples du chatbot Hydra DSL.

Ce script est destiné au build/CI. Le site Astro consomme ensuite uniquement le
JSON déjà validé ; aucun runtime Python n'est requis sur GitHub Pages.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS = (
    PROJECT_ROOT
    / "documentations"
    / "chatbot-hydra-dsl"
    / "examples"
    / "examples.json"
)

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hydra_etl.internal.engines.pandas_engine import PandasEngine  # noqa: E402
from hydra_etl.internal.parser.destination import DestinationParser  # noqa: E402
from hydra_etl.internal.parser.source import SourceParser  # noqa: E402
from hydra_etl.internal.parser.transform import TransformParser, _OP_MODEL_MAP  # noqa: E402
from hydra_etl.workflow.models import WorkflowDef  # noqa: E402


EXPECTED_NOTIONS = {
    "dsl.job_pipeline",
    "dsl.source",
    "dsl.destination",
    "transform.select",
    "transform.filter",
    "transform.calculate",
    "transform.cast",
    "transform.aggregate",
    "transform.join",
    "dsl.workflow",
}
EXPECTED_VARIANTS = {"minimal", "practical", "challenge", "correction"}


def _load_yaml(text: str) -> Any:
    value = yaml.safe_load(text)
    if value is None:
        raise ValueError("YAML vide")
    return value


def _normalise_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def _normalise_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {key: _normalise_value(value) for key, value in row.items()}
        for row in rows
    ]


def _validate_job(example: dict[str, Any]) -> None:
    files = example.get("files") or {}
    required = {"sources.yaml", "destinations.yaml", "pipeline.yaml"}
    missing = required - set(files)
    if missing:
        raise ValueError(f"manifests manquants: {sorted(missing)}")

    sources = SourceParser().parse(_load_yaml(files["sources.yaml"]))
    destinations = DestinationParser().parse(_load_yaml(files["destinations.yaml"]))

    if "transformations.yaml" in files:
        TransformParser().parse(_load_yaml(files["transformations.yaml"]))

    pipeline_doc = _load_yaml(files["pipeline.yaml"])
    pipeline = pipeline_doc.get("pipeline") if isinstance(pipeline_doc, dict) else None
    if not isinstance(pipeline, dict):
        raise ValueError("racine pipeline absente ou invalide")
    source_id = pipeline.get("from")
    destination_id = pipeline.get("to")
    if not isinstance(source_id, str) or not source_id.strip():
        raise ValueError("pipeline.from manquant ou invalide")
    if source_id not in sources.sources:
        raise ValueError(f"source inconnue: {source_id}")
    if not isinstance(destination_id, str) or not destination_id.strip():
        raise ValueError("pipeline.to manquant ou invalide")
    if destination_id not in destinations.destinations:
        raise ValueError(f"destination inconnue: {destination_id}")


def _validate_source(example: dict[str, Any]) -> None:
    SourceParser().parse(_load_yaml(example["yaml"]))


def _validate_destination(example: dict[str, Any]) -> None:
    DestinationParser().parse(_load_yaml(example["yaml"]))


def _validate_transformation(example: dict[str, Any]) -> None:
    parsed = _load_yaml(example["yaml"])
    if not isinstance(parsed, list) or len(parsed) != 1:
        raise ValueError("un exemple de transformation doit contenir exactement un step")
    step = parsed[0]
    if not isinstance(step, dict) or len(step) != 1:
        raise ValueError("step de transformation invalide")

    operation = next(iter(step))
    if operation != example.get("operation"):
        raise ValueError(
            f"operation déclarée '{example.get('operation')}' différente du YAML '{operation}'"
        )
    if operation not in _OP_MODEL_MAP:
        raise ValueError(f"opération inconnue: {operation}")

    # Valide avec le même parseur que le moteur Hydra.
    config = TransformParser().parse({"transformations": {"steps": parsed}})
    params = dict(config.steps[0].params)
    if "rightRows" in example:
        params["_right_rows"] = example["rightRows"]

    frame = pd.DataFrame(example.get("inputRows") or [])
    result = PandasEngine().apply_step(frame, {operation: params}).output

    if "expectedRows" not in example:
        raise ValueError("expectedRows requis pour un exemple de transformation valide")
    actual_rows = _normalise_rows(result.reset_index(drop=True).to_dict(orient="records"))
    expected_rows = _normalise_rows(example["expectedRows"])
    if actual_rows != expected_rows:
        raise AssertionError(
            "résultat différent\n"
            f"attendu={json.dumps(expected_rows, ensure_ascii=False)}\n"
            f"obtenu={json.dumps(actual_rows, ensure_ascii=False)}"
        )


def _validate_workflow_graph(workflow: WorkflowDef) -> None:
    names = {step.name for step in workflow.steps}
    for step in workflow.steps:
        unknown = set(step.depends_on) - names
        if unknown:
            raise ValueError(f"depends_on inconnu pour {step.name}: {sorted(unknown)}")

    visiting: set[str] = set()
    visited: set[str] = set()
    dependencies = {step.name: step.depends_on for step in workflow.steps}

    def visit(name: str) -> None:
        if name in visiting:
            raise ValueError(f"cycle détecté autour de {name}")
        if name in visited:
            return
        visiting.add(name)
        for dependency in dependencies[name]:
            visit(dependency)
        visiting.remove(name)
        visited.add(name)

    for name in names:
        visit(name)


def _validate_workflow(example: dict[str, Any]) -> None:
    document = _load_yaml(example["yaml"])
    workflow_data = document.get("workflow") if isinstance(document, dict) else None
    if not isinstance(workflow_data, dict):
        raise ValueError("racine workflow absente ou invalide")
    workflow = WorkflowDef.model_validate(workflow_data)
    _validate_workflow_graph(workflow)


VALIDATORS = {
    "job": _validate_job,
    "source": _validate_source,
    "destination": _validate_destination,
    "transformation": _validate_transformation,
    "workflow": _validate_workflow,
}


def _validate_structure(document: dict[str, Any]) -> list[dict[str, Any]]:
    if document.get("runtime") != "astro-static-github-pages":
        raise ValueError("runtime du corpus incorrect")
    examples = document.get("examples")
    if not isinstance(examples, list):
        raise ValueError("examples doit être une liste")
    if len(examples) != 40:
        raise ValueError(f"40 exemples attendus, {len(examples)} reçus")

    identifiers = [example.get("id") for example in examples]
    if any(not isinstance(identifier, str) or not identifier for identifier in identifiers):
        raise ValueError("chaque exemple doit posséder un id non vide")
    duplicates = [item for item, count in Counter(identifiers).items() if count > 1]
    if duplicates:
        raise ValueError(f"identifiants dupliqués: {duplicates}")

    notions = Counter(example.get("notion") for example in examples)
    if set(notions) != EXPECTED_NOTIONS:
        raise ValueError(f"notions incorrectes: {sorted(notions)}")
    if any(count != 4 for count in notions.values()):
        raise ValueError(f"chaque notion doit avoir 4 exemples: {dict(notions)}")

    for notion in EXPECTED_NOTIONS:
        variants = {
            example.get("variant")
            for example in examples
            if example.get("notion") == notion
        }
        if variants != EXPECTED_VARIANTS:
            raise ValueError(f"variantes incorrectes pour {notion}: {sorted(variants)}")

    required_text = {"title", "question", "answer"}
    for example in examples:
        missing = [field for field in required_text if not example.get(field)]
        if missing:
            raise ValueError(f"{example['id']}: champs textuels manquants {missing}")
        hints = example.get("hints")
        if not isinstance(hints, list) or len(hints) < 2:
            raise ValueError(f"{example['id']}: au moins deux indices sont requis")
        if example.get("validation") not in {"valid", "invalid"}:
            raise ValueError(f"{example['id']}: validation doit être valid ou invalid")
        if example.get("validation") == "invalid" and not example.get("expectedErrorContains"):
            raise ValueError(f"{example['id']}: expectedErrorContains requis")
        if example.get("kind") not in VALIDATORS:
            raise ValueError(f"{example['id']}: kind inconnu")
    return examples


def validate_corpus(path: Path) -> tuple[int, int]:
    document = json.loads(path.read_text(encoding="utf-8"))
    examples = _validate_structure(document)
    valid_count = 0
    invalid_count = 0

    for example in examples:
        validator = VALIDATORS[example["kind"]]
        try:
            validator(example)
        except Exception as error:
            if example["validation"] != "invalid":
                raise AssertionError(f"{example['id']} devrait être valide: {error}") from error
            expected = example["expectedErrorContains"].casefold()
            if expected not in str(error).casefold():
                raise AssertionError(
                    f"{example['id']}: erreur attendue contenant {expected!r}, obtenue {str(error)!r}"
                ) from error
            invalid_count += 1
        else:
            if example["validation"] != "valid":
                raise AssertionError(f"{example['id']} devrait être invalide")
            valid_count += 1
    return valid_count, invalid_count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    args = parser.parse_args()
    valid_count, invalid_count = validate_corpus(args.corpus.resolve())
    print(
        f"OK — {valid_count + invalid_count} exemples validés "
        f"({valid_count} valides, {invalid_count} défis invalides attendus)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
