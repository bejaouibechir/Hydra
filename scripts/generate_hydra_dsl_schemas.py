"""Génère les JSON Schema officiels du Hydra DSL depuis Pydantic.

Usage :
    python scripts/generate_hydra_dsl_schemas.py
    python scripts/generate_hydra_dsl_schemas.py --check

Le mode ``--check`` ne modifie aucun fichier et échoue si les artefacts présents
ne correspondent plus aux modèles Pydantic actifs.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Iterable, Type

from pydantic import BaseModel


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    PROJECT_ROOT / "documentations" / "chatbot-hydra-dsl" / "schemas"
)
JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"

# Permet d'exécuter le script directement depuis n'importe quel répertoire.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Regle 3.1 : la version produit vient de hydra_etl/__init__.py, jamais
# d'un litteral. La version du DSL est un numero distinct (Regle 3.2).
from hydra_etl import __version__ as PRODUCT_VERSION  # noqa: E402
from hydra_etl import DSL_VERSION  # noqa: E402  (Regle 3.2)

SCHEMA_BASE_ID = f"https://hydra.local/schemas/{PRODUCT_VERSION}"

from hydra_etl.internal.parser.destination import DestinationsConfig  # noqa: E402
from hydra_etl.internal.parser.source import SourcesConfig  # noqa: E402
from hydra_etl.internal.parser.transform import (  # noqa: E402
    TransformConfig,
    _OP_MODEL_MAP,
)


def _load_workflow_model() -> Type[BaseModel]:
    """Charge hydra_etl/workflow/models.py sans exécuter le __init__ du package.

    Le package importe son parseur YAML à l'initialisation. Cette dépendance
    d'exécution n'est pas nécessaire pour produire le JSON Schema du modèle.
    """
    module_name = "_hydra_schema_workflow_models"
    spec = importlib.util.spec_from_file_location(
        module_name, PROJECT_ROOT / "hydra_etl" / "workflow" / "models.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Impossible de charger hydra_etl/workflow/models.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module.WorkflowDef


WorkflowDef = _load_workflow_model()


def _source_model_name(model: Type[BaseModel]) -> str:
    if model is WorkflowDef:
        return "workflow.models.WorkflowDef"
    return f"{model.__module__}.{model.__name__}"


def _json_text(value: Any) -> str:
    """Sérialisation stable utilisée pour la génération et la vérification."""
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _schema_for(
    model: Type[BaseModel],
    *,
    schema_id: str,
    kind: str,
    dsl_name: str,
) -> dict[str, Any]:
    """Construit un schéma Pydantic enrichi uniquement de métadonnées Hydra."""
    schema = model.model_json_schema(mode="validation")
    schema["$schema"] = JSON_SCHEMA_DIALECT
    schema["$id"] = f"{SCHEMA_BASE_ID}/{schema_id}"
    schema["x-hydra"] = {
        "dslName": dsl_name,
        "dslVersion": DSL_VERSION,
        "generatedFromPydantic": True,
        "kind": kind,
        "productVersion": PRODUCT_VERSION,
        "sourceModel": _source_model_name(model),
    }
    return schema


def build_artifacts() -> dict[str, str]:
    """Retourne tous les fichiers attendus sous forme chemin relatif -> JSON."""
    artifacts: dict[str, str] = {}
    entries: list[dict[str, str]] = []

    top_level: Iterable[tuple[str, str, str, str, Type[BaseModel]]] = (
        ("manifests/sources.schema.json", "manifests/sources.schema.json", "manifest", "sources", SourcesConfig),
        ("manifests/transformations.schema.json", "manifests/transformations.schema.json", "manifest", "transformations", TransformConfig),
        ("manifests/destinations.schema.json", "manifests/destinations.schema.json", "manifest", "destinations", DestinationsConfig),
        ("manifests/workflow.schema.json", "manifests/workflow.schema.json", "manifest", "workflow", WorkflowDef),
    )

    for relative_path, schema_id, kind, dsl_name, model in top_level:
        schema = _schema_for(
            model,
            schema_id=schema_id,
            kind=kind,
            dsl_name=dsl_name,
        )
        artifacts[relative_path] = _json_text(schema)
        entries.append(
            {
                "dslName": dsl_name,
                "kind": kind,
                "path": relative_path,
                "sourceModel": _source_model_name(model),
            }
        )

    for operation, model in _OP_MODEL_MAP.items():
        relative_path = f"operations/{operation}.schema.json"
        schema = _schema_for(
            model,
            schema_id=relative_path,
            kind="transformation",
            dsl_name=operation,
        )
        artifacts[relative_path] = _json_text(schema)
        entries.append(
            {
                "dslName": operation,
                "kind": "transformation",
                "path": relative_path,
                "sourceModel": _source_model_name(model),
            }
        )

    index = {
        "$schema": JSON_SCHEMA_DIALECT,
        "dslVersion": DSL_VERSION,
        "generatedFrom": "Pydantic model_json_schema(mode='validation')",
        "productVersion": PRODUCT_VERSION,
        "schemaCount": len(entries),
        "schemas": entries,
        "unmodelledManifests": [
            {
                "name": "pipeline",
                "reason": "pipeline.yaml ne possède pas encore de modèle Pydantic actif",
            }
        ],
    }
    artifacts["index.json"] = _json_text(index)
    return artifacts


def write_artifacts(output_dir: Path, artifacts: dict[str, str]) -> None:
    for relative_path, content in artifacts.items():
        destination = output_dir / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8", newline="\n")


def check_artifacts(output_dir: Path, artifacts: dict[str, str]) -> list[str]:
    problems: list[str] = []
    for relative_path, expected in artifacts.items():
        destination = output_dir / relative_path
        if not destination.exists():
            problems.append(f"manquant: {relative_path}")
            continue
        actual = destination.read_text(encoding="utf-8")
        if actual != expected:
            problems.append(f"obsolète: {relative_path}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Dossier de sortie (défaut: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Vérifie les fichiers générés sans les modifier.",
    )
    args = parser.parse_args()

    output_dir = args.output.resolve()
    artifacts = build_artifacts()

    if args.check:
        problems = check_artifacts(output_dir, artifacts)
        if problems:
            print("Schémas Hydra DSL non synchronisés :")
            for problem in problems:
                print(f"- {problem}")
            return 1
        print(f"OK — {len(artifacts) - 1} schémas synchronisés dans {output_dir}")
        return 0

    write_artifacts(output_dir, artifacts)
    print(f"Généré — {len(artifacts) - 1} schémas dans {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
