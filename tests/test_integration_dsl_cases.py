"""
Tests d'intégration fictifs (sans engines) basés sur des cas YAML externes.

Objectif :
- Charger des cas DSL depuis tests/fixtures/dsl_cases/<case_name>/
- Résoudre ${ENV:...} / ${SECRET:...}
- Parser/valider strictement : SourceParser, DestinationParser, TransformParser
- Vérifier la cohérence pipeline (from/to)

Règle :
- Tout dossier ok_* doit PASSER.
- Tout dossier ko_* doit ECHOUER.
- Le type d'erreur attendu est déduit du nom du dossier (simple et efficace).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable

import pytest
import yaml
from pydantic import ValidationError

from internal.config.secrets import SecretResolver, SecretResolutionError
from internal.parser.source import SourceParser
from internal.parser.destination import DestinationParser
from internal.parser.transform import TransformParser


# ----------------------------
# Chargement YAML
# ----------------------------

@dataclass(frozen=True)
class CaseFiles:
    """
    Fichiers attendus pour un cas DSL.
    """
    sources: Path
    destinations: Path
    pipeline: Path
    transformations: Path


def _load_yaml_dict(path: Path) -> Dict[str, Any]:
    """
    Charge un YAML et garantit un dict (ou {} si vide).
    """
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML invalide (dict attendu) : {path}")
    return data


def _case_files(case_dir: Path) -> CaseFiles:
    """
    Résout les 4 fichiers standards d'un cas.
    """
    files = {
        "sources": case_dir / "sources.yaml",
        "destinations": case_dir / "destinations.yaml",
        "pipeline": case_dir / "pipeline.yaml",
        "transformations": case_dir / "transformations.yaml",
    }

    missing = [str(p) for p in files.values() if not p.exists()]
    if missing:
        raise FileNotFoundError(f"Fichiers manquants dans {case_dir}: {', '.join(missing)}")

    return CaseFiles(**files)  # type: ignore[arg-type]


def _coherence_check(pipeline_raw: Dict[str, Any], source_names: set[str], destination_names: set[str]) -> None:
    """
    Vérifie une cohérence minimale de wiring.

    Convention MVP :
      pipeline:
        from: <source_name>
        to: <destination_name>
    """
    if "pipeline" not in pipeline_raw or not isinstance(pipeline_raw["pipeline"], dict):
        raise ValueError("pipeline.yaml doit contenir une clé 'pipeline' (dict)")

    p = pipeline_raw["pipeline"]
    src = p.get("from")
    dst = p.get("to")

    if not isinstance(src, str) or not src.strip():
        raise ValueError("pipeline.from est obligatoire (string non vide)")
    if not isinstance(dst, str) or not dst.strip():
        raise ValueError("pipeline.to est obligatoire (string non vide)")

    if src not in source_names:
        raise ValueError(f"pipeline.from référence une source inconnue: {src}")
    if dst not in destination_names:
        raise ValueError(f"pipeline.to référence une destination inconnue: {dst}")


def _run_case(case_dir: Path, *, secrets: Dict[str, Any]) -> None:
    """
    Exécute un cas :
    - charge les 4 YAML
    - résout secrets/env
    - parse strictement
    - vérifie la cohérence pipeline
    """
    files = _case_files(case_dir)

    raw_sources = _load_yaml_dict(files.sources)
    raw_destinations = _load_yaml_dict(files.destinations)
    raw_pipeline = _load_yaml_dict(files.pipeline)
    raw_transformations = _load_yaml_dict(files.transformations)

    resolver = SecretResolver(secrets=secrets)

    sources_resolved = resolver.resolve(raw_sources)
    destinations_resolved = resolver.resolve(raw_destinations)
    pipeline_resolved = resolver.resolve(raw_pipeline)
    transformations_resolved = resolver.resolve(raw_transformations)

    src_cfg = SourceParser().parse(sources_resolved)
    dst_cfg = DestinationParser().parse(destinations_resolved)
    tf_cfg = TransformParser().parse(transformations_resolved)

    # Sanity : un cas OK doit avoir au moins 1 step
    assert len(tf_cfg.steps) >= 1

    _coherence_check(
        pipeline_raw=pipeline_resolved,
        source_names=set(src_cfg.sources.keys()),
        destination_names=set(dst_cfg.destinations.keys()),
    )


# ----------------------------
# Découverte des cas
# ----------------------------

def _cases_dir() -> Path:
    """
    Racine des cas DSL.
    """
    return Path(__file__).parent / "fixtures" / "dsl_cases"


def _list_case_dirs(prefix: str) -> list[Path]:
    """
    Liste les dossiers case par préfixe (ok_*, ko_*), à plat.
    """
    base = _cases_dir()
    if not base.exists():
        return []
    return sorted([p for p in base.iterdir() if p.is_dir() and p.name.startswith(prefix)])


def _expected_exception_for_ko(case_dir: Path):
    """
    Déduit le type d'erreur attendu à partir du nom du dossier.

    But :
    - Rendre les KO très explicites et éviter un "catch-all" trop permissif.
    """
    name = case_dir.name

    # Résolution ENV/SECRET
    if "missing_env" in name:
        return SecretResolutionError

    # Cohérence pipeline
    if "pipeline_unknown" in name or "unknown_source" in name:
        return ValueError

    # Tout ce qui touche transformations (structure/validation)
    # - op inconnue
    # - step mal formé
    # - params manquants
    # - cast invalide
    return (ValueError, ValidationError)


# ----------------------------
# Tests
# ----------------------------

@pytest.mark.parametrize("case_dir", _list_case_dirs("ok_"))
def test_dsl_cases_ok(monkeypatch, case_dir: Path):
    """
    Tous les cas ok_* doivent passer.
    """
    # ENV minimales pour les cas OK
    monkeypatch.setenv("DB_HOST", "127.0.0.1")

    secrets = {
        "db.password": "p@ss",
    }

    _run_case(case_dir, secrets=secrets)


@pytest.mark.parametrize("case_dir", _list_case_dirs("ko_"))
def test_dsl_cases_ko(monkeypatch, case_dir: Path):
    """
    Tous les cas ko_* doivent échouer avec un type d'erreur attendu.
    """
    # Certains KO ont quand même besoin d'ENV présente (sauf missing_env)
    if "missing_env" not in case_dir.name:
        monkeypatch.setenv("DB_HOST", "127.0.0.1")

    secrets = {
        "db.password": "p@ss",
    }

    expected = _expected_exception_for_ko(case_dir)

    with pytest.raises(expected):
        _run_case(case_dir, secrets=secrets)
