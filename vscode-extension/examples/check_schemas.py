#!/usr/bin/env python3
"""
Check the JSON schemas shipped with the HYDRA ETL extension.

1. Every schema is valid JSON and conforms to the draft-07 meta-schema.
2. Manifests under examples/valid_* validate without a single error.
3. Manifests under examples/invalid_* do raise the errors they advertise.

Usage:
    pip install jsonschema pyyaml
    python examples/check_schemas.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import yaml
    from jsonschema import Draft7Validator
except ImportError:
    sys.exit("Missing dependencies: pip install jsonschema pyyaml")

ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = ROOT / "schemas"
EXAMPLES_DIR = ROOT / "examples"

# manifest file name -> schema file name
MAPPING = {
    "sources.yaml": "sources.schema.json",
    "destinations.yaml": "destinations.schema.json",
    "pipeline.yaml": "pipeline.schema.json",
    "transformations.yaml": "transformations.schema.json",
    "workflow.yaml": "workflow.schema.json",
}

OK, KO = "  OK  ", "  KO  "
failures: list[str] = []


def load_schema(name: str) -> dict:
    return json.loads((SCHEMAS_DIR / name).read_text(encoding="utf-8"))


def check_meta() -> dict[str, dict]:
    print("\n=== 1. Schema validity ===")
    schemas: dict[str, dict] = {}
    for name in sorted(MAPPING.values()):
        try:
            schema = load_schema(name)
            Draft7Validator.check_schema(schema)
            schemas[name] = schema
            print(f"[{OK}] {name}")
        except Exception as exc:
            failures.append(f"{name}: {exc}")
            print(f"[{KO}] {name} — {exc}")
    return schemas


def errors_for(path: Path, schema: dict) -> list:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return sorted(Draft7Validator(schema).iter_errors(data), key=lambda e: list(e.path))


def check_valid(schemas: dict[str, dict]) -> None:
    print("\n=== 2. Valid manifests (no error expected) ===")
    for folder in sorted(EXAMPLES_DIR.glob("valid_*")):
        for path in sorted(folder.rglob("*.yaml")):
            schema_name = MAPPING.get(path.name)
            if not schema_name or schema_name not in schemas:
                continue
            errors = errors_for(path, schemas[schema_name])
            rel = path.relative_to(ROOT)
            if errors:
                failures.append(f"{rel}: {len(errors)} unexpected error(s)")
                print(f"[{KO}] {rel}")
                for err in errors:
                    loc = " / ".join(str(p) for p in err.path) or "(root)"
                    print(f"         {loc} -> {err.message}")
            else:
                print(f"[{OK}] {rel}")


def check_invalid(schemas: dict[str, dict]) -> None:
    print("\n=== 3. Faulty manifests (errors expected) ===")
    for folder in sorted(EXAMPLES_DIR.glob("invalid_*")):
        for path in sorted(folder.rglob("*.yaml")):
            schema_name = MAPPING.get(path.name)
            if not schema_name or schema_name not in schemas:
                continue
            errors = errors_for(path, schemas[schema_name])
            rel = path.relative_to(ROOT)
            if errors:
                print(f"[{OK}] {rel} — {len(errors)} error(s) caught")
                for err in errors:
                    loc = " / ".join(str(p) for p in err.path) or "(root)"
                    print(f"         {loc} -> {err.message[:110]}")
            else:
                failures.append(f"{rel}: no error caught, though some are expected")
                print(f"[{KO}] {rel} — no error caught")


def main() -> int:
    schemas = check_meta()
    check_valid(schemas)
    check_invalid(schemas)

    print("\n" + "=" * 60)
    if failures:
        print(f"FAILED — {len(failures)} problem(s):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("PASSED — every check succeeded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
