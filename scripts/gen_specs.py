# -*- coding: utf-8 -*-
"""
Tableaux de specification du site, generes depuis les modeles Pydantic du moteur.

Aucune fiche du DSL n'est ecrite a la main : chaque cle, chaque type, chaque valeur par
defaut et chaque contrainte vient de `model_json_schema()`. Un changement du moteur se
propage au site en relancant ce script.

Sortie : hydra-site/src/data/dsl-specs.json
Usage  : python scripts/gen_specs.py
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

OUT = os.path.join(os.path.dirname(ROOT), "hydra-site", "src", "data", "dsl-specs.json")

from hydra_etl.internal.parser import transform as T          # noqa: E402
from hydra_etl.internal.parser import source as S             # noqa: E402
from hydra_etl.internal.parser import destination as D        # noqa: E402
from hydra_etl.workflow import models as W                    # noqa: E402


def type_label(prop: dict) -> str:
    """Rend un type JSON Schema lisible par un humain."""
    if "anyOf" in prop:
        parts = [type_label(p) for p in prop["anyOf"] if p.get("type") != "null"]
        return " | ".join(dict.fromkeys(parts)) or "any"
    if "enum" in prop:
        return " · ".join(str(v) for v in prop["enum"])
    if "const" in prop:
        return str(prop["const"])
    t = prop.get("type")
    if t == "array":
        return f'list[{type_label(prop.get("items", {}))}]'
    if t == "object":
        extra = prop.get("additionalProperties")
        if isinstance(extra, dict):
            return f"mapping[{type_label(extra)}]"
        return "mapping"
    return {"integer": "int", "number": "float", "string": "string",
            "boolean": "bool", "null": "null"}.get(t, t or "any")


def constraint_label(prop: dict) -> str:
    """Extrait les contraintes reellement portees par le modele."""
    bits = []
    for key, fmt in (("minLength", "au moins {} caractere(s)"), ("maxLength", "au plus {} caracteres"),
                     ("minItems", "au moins {} element(s)"), ("maxItems", "au plus {} elements"),
                     ("minimum", "minimum {}"), ("maximum", "maximum {}"),
                     ("exclusiveMinimum", "strictement superieur a {}"),
                     ("exclusiveMaximum", "strictement inferieur a {}")):
        if key in prop:
            bits.append(fmt.format(prop[key]))
    for sub in prop.get("anyOf", []):
        bits.extend(b for b in [constraint_label(sub)] if b)
    if "enum" in prop:
        bits.append("valeurs : " + " · ".join(str(v) for v in prop["enum"]))
    return " · ".join(dict.fromkeys(bits))


def spec_of(model) -> dict:
    schema = model.model_json_schema()
    required = set(schema.get("required", []))
    keys = []
    for name, prop in schema.get("properties", {}).items():
        default = prop.get("default", None)
        keys.append({
            "key": name,
            "type": type_label(prop),
            "required": name in required,
            "default": None if default is None else default,
            "constraint": constraint_label(prop),
            "description": prop.get("description", "") or "",
        })
    return {"model": model.__name__, "keys": keys}


BLOCKS = {
    # operations de transformation — les 18 du moteur
    **{f"op.{name}": model for name, model in T._OP_MODEL_MAP.items()},
    # blocs du manifeste
    "transformations": T.TransformConfig,
    "transformations.step": T.TransformStep,
    "sources.<id>": S.SourceDefinition,
    "sources.<id>.extract": S.ExtractConfig,
    "sources.<id>.schema": S.SchemaConfig,
    "sources.<id>.schema.fields": S.SchemaFieldConfig,
    "destinations.<id>": D.DestinationDefinition,
    "destinations.<id>.load": D.LoadConfig,
    # workflow
    "workflow": W.WorkflowDef,
    "workflow.trigger": W.Trigger,
    "workflow.steps": W.WorkflowStep,
    "workflow.steps.retry": W.RetryPolicy,
}

if __name__ == "__main__":
    specs = {}
    for label, model in BLOCKS.items():
        try:
            specs[label] = spec_of(model)
        except Exception as e:  # un modele non introspectable doit se voir, pas disparaitre
            specs[label] = {"model": getattr(model, "__name__", "?"), "keys": [], "error": str(e)}
            print(f"  ATTENTION {label} : {e}")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"generated_from": "pydantic model_json_schema()", "blocks": specs},
                  f, ensure_ascii=False, indent=1)
        f.write("\n")

    ops = [k for k in specs if k.startswith("op.")]
    print(f"{len(specs)} blocs generes — dont {len(ops)} operations")
    for label in sorted(specs):
        n = len(specs[label]["keys"])
        print(f"  {label:34} {n} cle(s)")
    print("\necrit", OUT)
