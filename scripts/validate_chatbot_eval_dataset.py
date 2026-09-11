"""Valide la structure et les références du dataset d'évaluation du chatbot."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = (
    PROJECT_ROOT
    / "documentations"
    / "chatbot-hydra-dsl"
    / "evaluation"
    / "eval-dataset.json"
)
DEFAULT_CORPUS = (
    PROJECT_ROOT
    / "documentations"
    / "chatbot-hydra-dsl"
    / "examples"
    / "examples.json"
)

EXPECTED_DISTRIBUTION = {
    "conceptual": 30,
    "dsl_error": 30,
    "example_request": 20,
    "out_of_scope": 10,
    "version_compatibility": 10,
}


def validate_dataset(
    dataset_path: Path = DEFAULT_DATASET,
    corpus_path: Path = DEFAULT_CORPUS,
) -> dict[str, int]:
    dataset: dict[str, Any] = json.loads(dataset_path.read_text(encoding="utf-8"))
    corpus: dict[str, Any] = json.loads(corpus_path.read_text(encoding="utf-8"))
    cases = dataset.get("cases")
    if not isinstance(cases, list):
        raise ValueError("cases doit être une liste")
    if dataset.get("totalCases") != 100 or len(cases) != 100:
        raise ValueError("le dataset doit contenir exactement 100 cas")
    if dataset.get("publishWithAstro") is not False:
        raise ValueError("le dataset d'évaluation ne doit pas être publié avec Astro")

    identifiers = [case.get("id") for case in cases]
    if len(set(identifiers)) != len(identifiers):
        duplicates = [item for item, count in Counter(identifiers).items() if count > 1]
        raise ValueError(f"identifiants dupliqués: {duplicates}")
    if any(not isinstance(identifier, str) or not identifier for identifier in identifiers):
        raise ValueError("chaque cas doit avoir un identifiant")

    distribution = dict(Counter(case.get("category") for case in cases))
    if distribution != EXPECTED_DISTRIBUTION:
        raise ValueError(f"distribution incorrecte: {distribution}")
    if dataset.get("distribution") != EXPECTED_DISTRIBUTION:
        raise ValueError("les métadonnées distribution sont incorrectes")

    weights = dataset.get("evaluationPolicy", {}).get("weights", {})
    if abs(sum(weights.values()) - 1.0) > 1e-9:
        raise ValueError("les poids d'évaluation doivent totaliser 1")
    threshold = dataset.get("evaluationPolicy", {}).get("passThreshold")
    if not isinstance(threshold, (int, float)) or not 0 < threshold <= 1:
        raise ValueError("passThreshold invalide")

    example_ids = {example["id"] for example in corpus["examples"]}
    for case in cases:
        if not case.get("prompt"):
            raise ValueError(f"{case['id']}: prompt manquant")
        context = case.get("context")
        expected = case.get("expected")
        if not isinstance(context, dict) or not isinstance(expected, dict):
            raise ValueError(f"{case['id']}: context ou expected invalide")
        if context.get("hydraVersion") != dataset.get("productVersion"):
            raise ValueError(f"{case['id']}: version Hydra incohérente")
        if context.get("dslVersion") != dataset.get("dslVersion"):
            raise ValueError(f"{case['id']}: version DSL incohérente")
        if not expected.get("referenceAnswer"):
            raise ValueError(f"{case['id']}: réponse de référence manquante")
        if not isinstance(expected.get("forbiddenClaims"), list):
            raise ValueError(f"{case['id']}: forbiddenClaims manquant")
        if not isinstance(expected.get("maxWords"), int):
            raise ValueError(f"{case['id']}: maxWords invalide")

        reference_example = context.get("referenceExampleId")
        if reference_example and reference_example not in example_ids:
            raise ValueError(f"{case['id']}: exemple de référence inconnu")

        for source in expected.get("mustCiteSources", []):
            source_path = PROJECT_ROOT / source
            if not source_path.is_file():
                raise ValueError(f"{case['id']}: source inexistante {source}")

        if expected.get("assistanceLevel") == "hint_1" and expected.get("revealSolution"):
            raise ValueError(f"{case['id']}: un premier indice ne doit pas révéler la solution")

    secret_case = next(case for case in cases if case["id"] == "eval-scope-secret-pasted")
    if "super-secret-123" in secret_case["expected"]["referenceAnswer"]:
        raise ValueError("la réponse de référence répète le secret synthétique")

    return distribution


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    args = parser.parse_args()
    distribution = validate_dataset(args.dataset.resolve(), args.corpus.resolve())
    print(
        "OK — dataset d'évaluation valide : "
        + ", ".join(f"{name}={count}" for name, count in distribution.items())
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
