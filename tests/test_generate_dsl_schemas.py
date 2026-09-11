import json
from pathlib import Path

from hydra_etl import __version__
from scripts.generate_hydra_dsl_schemas import (
    DEFAULT_OUTPUT,
    _OP_MODEL_MAP,
    build_artifacts,
    check_artifacts,
)


def test_generated_schema_inventory_is_complete() -> None:
    artifacts = build_artifacts()
    index = json.loads(artifacts["index.json"])

    assert index["schemaCount"] == 22
    assert len(index["schemas"]) == 22

    generated_operations = {
        entry["dslName"]
        for entry in index["schemas"]
        if entry["kind"] == "transformation"
    }
    assert generated_operations == set(_OP_MODEL_MAP)


def test_every_generated_schema_has_hydra_metadata() -> None:
    artifacts = build_artifacts()

    for relative_path, content in artifacts.items():
        if not relative_path.endswith(".schema.json"):
            continue
        schema = json.loads(content)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        # Regle 3.1 : pas de litteral de version dans les tests non plus.
        assert schema["$id"].startswith(f"https://hydra.local/schemas/{__version__}/")
        assert schema["x-hydra"]["generatedFromPydantic"] is True
        assert schema["x-hydra"]["sourceModel"]


def test_committed_schemas_are_synchronised() -> None:
    assert check_artifacts(Path(DEFAULT_OUTPUT), build_artifacts()) == []
