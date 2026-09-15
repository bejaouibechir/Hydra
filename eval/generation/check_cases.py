#!/usr/bin/env python3
"""
check_cases.py — Vérifie que le jeu d'évaluation « génération » ne référence
que des éléments qui existent réellement dans le DSL.

Un jeu d'évaluation faux est pire que pas de jeu du tout : il fait échouer des
réponses correctes. Ce script est le garde-fou, à lancer en CI avec
`tools/spec_export.py --check`.

Usage : python eval/generation/check_cases.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "documentations" / "chatbot-hydra-dsl" / "schemas"
CASES = Path(__file__).resolve().parent / "cases.json"

VALID_FILES = {
    "sources.yaml", "destinations.yaml", "transformations.yaml",
    "pipeline.yaml", "workflow.yaml",
}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    index = load(SCHEMAS / "index.json")
    operations = {e["dslName"] for e in index["schemas"] if e["kind"] == "transformation"}
    connectors = set(load(SCHEMAS / "connectors.schema.json")["enum"])
    actions = set(load(SCHEMAS / "actions.schema.json")["enum"])

    data = load(CASES)
    errors: list[str] = []

    for case in data["cases"]:
        cid = case["id"]
        exp = case.get("expect", {})

        for key in ("ops", "opsAny"):
            for op in exp.get(key, []):
                if op not in operations:
                    errors.append(f"{cid}: opération inconnue '{op}'")

        for key in ("sourceTypes", "destTypeAlt"):
            for t in exp.get(key, []):
                if t not in connectors:
                    errors.append(f"{cid}: connecteur inconnu '{t}'")

        dest = exp.get("destType")
        if dest and dest not in connectors:
            errors.append(f"{cid}: connecteur de destination inconnu '{dest}'")

        mode = exp.get("destMode")
        if mode and mode not in {"append", "replace", "upsert"}:
            errors.append(f"{cid}: mode de chargement inconnu '{mode}'")

        for f in exp.get("files", []):
            if f not in VALID_FILES:
                errors.append(f"{cid}: manifeste inconnu '{f}'")

        for a in exp.get("workflow", {}).get("actions", []):
            if a not in actions:
                errors.append(f"{cid}: action inconnue '{a}'")

        if case["level"] == "adversarial" and not exp.get("mustRefuse"):
            errors.append(f"{cid}: cas adversarial sans 'mustRefuse'")

    if errors:
        print(f"{len(errors)} incohérence(s) dans le jeu d'évaluation :")
        for e in errors:
            print("  -", e)
        return 1

    print(f"Jeu d'évaluation cohérent : {len(data['cases'])} cas, "
          f"{len(operations)} opérations, {len(connectors)} connecteurs, "
          f"{len(actions)} actions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
