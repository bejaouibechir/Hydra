#!/usr/bin/env python3
"""
spec_export.py — Génère la spécification complète du Hydra DSL DEPUIS LE CODE.

Source de vérité : les modèles Pydantic et les registres du moteur. Rien n'est
écrit à la main ici : toute évolution du code se propage automatiquement.

Sorties (par défaut sous documentations/chatbot-hydra-dsl/schemas/) :
  manifests/<nom>.schema.json      5 manifestes
  operations/<nom>.schema.json     les 18 opérations de transformation
  actions.schema.json              les actions de workflow
  index.json                       inventaire machine
  DSL_REFERENCE.md                 référence lisible (même source)

Usage :
  python tools/spec_export.py              # régénère
  python tools/spec_export.py --check      # CI : échoue si la spec a dérivé
  python tools/spec_export.py --out DIR    # autre répertoire de sortie
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEFAULT_OUT = ROOT / "documentations" / "chatbot-hydra-dsl" / "schemas"
RUNNER_PY = ROOT / "hydra_etl" / "workflow" / "runner.py"
REGISTRY_PY = ROOT / "hydra_etl" / "internal" / "connector" / "registry.py"

JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"


# --------------------------------------------------------------------------
# Découverte — aucune liste écrite à la main
# --------------------------------------------------------------------------

def discover_manifests() -> Dict[str, Any]:
    from hydra_etl.internal.parser.source import SourcesConfig
    from hydra_etl.internal.parser.destination import DestinationsConfig
    from hydra_etl.internal.parser.transform import TransformConfig
    from hydra_etl.internal.parser.pipeline import PipelineConfig
    from hydra_etl.workflow.models import WorkflowDef

    return {
        "sources": SourcesConfig,
        "transformations": TransformConfig,
        "destinations": DestinationsConfig,
        "pipeline": PipelineConfig,
        "workflow": WorkflowDef,
    }


def discover_operations() -> Dict[str, Any]:
    """Les 18 opérations, lues dans le registre réel du parseur."""
    from hydra_etl.internal.parser.transform import _OP_MODEL_MAP
    return dict(_OP_MODEL_MAP)


def discover_actions() -> list[str]:
    """
    Actions de workflow, extraites par analyse syntaxique de la table
    `action_handlers` du runner. Pas de duplication, pas de dérive possible.
    """
    tree = ast.parse(RUNNER_PY.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if "action_handlers" not in targets:
            continue
        if not isinstance(node.value, ast.Dict):
            continue
        return sorted(
            k.value for k in node.value.keys
            if isinstance(k, ast.Constant) and isinstance(k.value, str)
        )
    raise RuntimeError(
        "Table 'action_handlers' introuvable dans workflow/runner.py — "
        "le nom a changé, corriger spec_export.py."
    )


def dsl_version() -> str:
    try:
        from hydra_etl.internal.dsl_version import DSL_VERSION
        return str(DSL_VERSION)
    except Exception:
        return "1.0"


def discover_connectors() -> list[str]:
    """
    Types de connecteurs, extraits par analyse syntaxique de CONNECTOR_REGISTRY.

    L'analyse statique est volontaire : à l'exécution, les connecteurs à
    dépendances optionnelles (mongodb, parquet, web_api) ne s'enregistrent que
    si leur extra est installé. La spécification, elle, doit lister TOUS les
    types du DSL, quelle que soit l'installation locale.
    """
    tree = ast.parse(REGISTRY_PY.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        # CONNECTOR_REGISTRY = { "csv": ..., ... }
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = [t.id for t in targets if isinstance(t, ast.Name)]
            if "CONNECTOR_REGISTRY" in names and isinstance(node.value, ast.Dict):
                found.update(
                    k.value for k in node.value.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)
                )
        # CONNECTOR_REGISTRY["mongodb"] = ...
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if (isinstance(t, ast.Subscript)
                        and isinstance(t.value, ast.Name)
                        and t.value.id == "CONNECTOR_REGISTRY"
                        and isinstance(t.slice, ast.Constant)
                        and isinstance(t.slice.value, str)):
                    found.add(t.slice.value)
    if not found:
        raise RuntimeError("CONNECTOR_REGISTRY introuvable — corriger spec_export.py.")
    return sorted(found)


def product_version() -> str:
    try:
        import hydra_etl
        return getattr(hydra_etl, "__version__", "unknown")
    except Exception:
        return "unknown"


# --------------------------------------------------------------------------
# Génération
# --------------------------------------------------------------------------

def schema_of(model: Any, title: str, kind: str, dsl_name: str) -> Dict[str, Any]:
    """JSON Schema du modèle, enrichi des métadonnées Hydra (compatibilité)."""
    s = model.model_json_schema(mode="validation")
    s["$schema"] = JSON_SCHEMA_DIALECT
    s.setdefault("title", title)
    folder = "manifests" if kind == "manifest" else "operations"
    s["$id"] = (
        f"https://hydra.local/schemas/{product_version()}/"
        f"{folder}/{dsl_name}.schema.json"
    )
    s["x-hydra"] = {
        "dslName": dsl_name,
        "dslVersion": dsl_version(),
        "generatedFromPydantic": True,
        "kind": kind,
        "productVersion": product_version(),
        "sourceModel": f"{model.__module__}.{model.__name__}",
    }
    return s


def actions_schema(actions: list[str]) -> Dict[str, Any]:
    return {
        "$schema": JSON_SCHEMA_DIALECT,
        "title": "Hydra workflow actions",
        "description": (
            "Actions acceptées par un step de type 'action'. "
            "Toute valeur hors de cette liste est ignorée à l'exécution : "
            "une faute de frappe ne provoque PAS d'erreur."
        ),
        "type": "string",
        "enum": actions,
        "x-hydra": {
            "dslName": "actions",
            "dslVersion": dsl_version(),
            "kind": "actions",
            "productVersion": product_version(),
            "sourceModel": "hydra_etl.workflow.runner.action_handlers",
        },
    }


def connectors_schema(connectors: list[str]) -> Dict[str, Any]:
    return {
        "$schema": JSON_SCHEMA_DIALECT,
        "title": "Hydra connector types",
        "description": (
            "Valeurs admises pour la clé 'type' d'une source ou d'une "
            "destination. Le modèle Pydantic accepte une chaîne libre : seul le "
            "registre fait foi, et un type inconnu n'échoue qu'à l'exécution. "
            "Cette énumération existe pour contraindre la génération en amont."
        ),
        "type": "string",
        "enum": connectors,
        "x-hydra": {
            "dslName": "connectors",
            "dslVersion": dsl_version(),
            "kind": "connectors",
            "productVersion": product_version(),
            "sourceModel": "hydra_etl.internal.connector.registry.CONNECTOR_REGISTRY",
            "note": (
                "mongodb, parquet et web_api ne s'enregistrent que si leur "
                "extra est installé ; ils font partie du DSL dans tous les cas."
            ),
        },
    }


def build(out: Path) -> Dict[str, str]:
    """Retourne {chemin relatif: contenu JSON/markdown}."""
    files: Dict[str, str] = {}

    def dump(rel: str, payload: Any) -> None:
        files[rel] = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    manifests = discover_manifests()
    operations = discover_operations()
    actions = discover_actions()
    connectors = discover_connectors()

    index_entries = []

    for name, model in sorted(manifests.items()):
        rel = f"manifests/{name}.schema.json"
        dump(rel, schema_of(model, f"Hydra manifest — {name}", "manifest", name))
        index_entries.append({
            "kind": "manifest", "dslName": name, "path": rel,
            "sourceModel": f"{model.__module__}.{model.__name__}",
        })

    for name, model in sorted(operations.items()):
        rel = f"operations/{name}.schema.json"
        dump(rel, schema_of(model, f"Hydra transformation — {name}", "transformation", name))
        index_entries.append({
            "kind": "transformation", "dslName": name, "path": rel,
            "sourceModel": f"{model.__module__}.{model.__name__}",
        })

    dump("actions.schema.json", actions_schema(actions))
    dump("connectors.schema.json", connectors_schema(connectors))
    index_entries.append({
        "kind": "connectors", "dslName": "connectors", "path": "connectors.schema.json",
        "sourceModel": "hydra_etl.internal.connector.registry.CONNECTOR_REGISTRY",
    })
    index_entries.append({
        "kind": "actions", "dslName": "actions", "path": "actions.schema.json",
        "sourceModel": "hydra_etl.workflow.runner.action_handlers",
    })

    dump("index.json", {
        "$schema": JSON_SCHEMA_DIALECT,
        "generatedBy": "tools/spec_export.py",
        "generatedFrom": "Pydantic model_json_schema(mode='validation') + AST du runner",
        "productVersion": product_version(),
        "dslVersion": dsl_version(),
        "unmodelledManifests": [],
        "manifestCount": len(manifests),
        "operationCount": len(operations),
        "actionCount": len(actions),
        "connectorCount": len(connectors),
        "connectors": connectors,
        "schemaCount": len(index_entries),
        "actions": actions,
        "schemas": sorted(index_entries, key=lambda e: (e["kind"], e["dslName"])),
    })

    files["DSL_REFERENCE.md"] = reference_markdown(manifests, operations, actions, connectors)
    return files


def reference_markdown(manifests, operations, actions, connectors) -> str:
    def required_of(model) -> str:
        req = model.model_json_schema(mode="validation").get("required", [])
        return ", ".join(f"`{r}`" for r in req) if req else "—"

    lines = [
        "# Référence du Hydra DSL",
        "",
        "> **Fichier généré** par `tools/spec_export.py` depuis les modèles du",
        "> moteur. Ne pas modifier à la main : toute correction se fait dans le",
        "> code, puis on régénère.",
        "",
        f"Version du produit : **{product_version()}**",
        "",
        f"## Connecteurs ({len(connectors)})",
        "",
        ", ".join(f"`{c}`" for c in connectors),
        "",
        "> `postgres`/`postgresql` et `mysql`/`mariadb` sont des alias.",
        "> `mongodb`, `parquet` et `web_api` ne s'enregistrent qu'avec leur extra",
        "> installé, mais font partie du DSL dans tous les cas.",
        "",
        "## Manifestes",
        "",
        "| Manifeste | Modèle source | Clés obligatoires |",
        "|---|---|---|",
    ]
    for name, model in sorted(manifests.items()):
        lines.append(f"| `{name}.yaml` | `{model.__module__}.{model.__name__}` | {required_of(model)} |")

    lines += [
        "",
        f"## Opérations de transformation ({len(operations)})",
        "",
        "| Opération | Clés obligatoires |",
        "|---|---|",
    ]
    for name, model in sorted(operations.items()):
        lines.append(f"| `{name}` | {required_of(model)} |")

    lines += [
        "",
        f"## Actions de workflow ({len(actions)})",
        "",
        ", ".join(f"`{a}`" for a in actions),
        "",
        "> Attention : une action inconnue est **ignorée silencieusement** à",
        "> l'exécution et le step est compté comme réussi. Une faute de frappe",
        "> ne se voit donc pas.",
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Génère la spécification du Hydra DSL depuis le code.")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--check", action="store_true", help="CI : échoue si la spec committée a dérivé du code.")
    args = ap.parse_args()

    files = build(args.out)

    if args.check:
        drift = []
        for rel, content in files.items():
            p = args.out / rel
            if not p.exists() or p.read_text(encoding="utf-8") != content:
                drift.append(rel)
        if drift:
            print("SPEC DESYNCHRONISEE — regenerer avec: python tools/spec_export.py")
            for d in sorted(drift):
                print("  -", d)
            return 1
        print(f"Spec a jour ({len(files)} fichiers).")
        return 0

    for rel, content in files.items():
        p = args.out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    print(f"Spec generee dans {args.out}")
    print(f"  manifestes : {len(discover_manifests())}")
    print(f"  operations : {len(discover_operations())}")
    print(f"  actions    : {len(discover_actions())}")
    print(f"  connecteurs: {len(discover_connectors())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
