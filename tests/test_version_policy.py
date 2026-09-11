# -*- coding: utf-8 -*-
"""
tests/test_version_policy.py — Garde-fou de la Regle 3 (versionnage).

Trois numeros circulent dans Hydra et se sont deja desynchronises :

    version PRODUIT   hydra_etl.__version__   -> wheel, CLI, API, Studio
    version DSL       hydra_etl.DSL_VERSION   -> champ `version:` des manifests
    version OpenAPI   FastAPI(version=...)    -> visible sur /docs

Ces tests verifient qu'ils ont chacun UNE source, et qu'aucun litteral n'est
reintroduit ailleurs dans le code. C'est ce qui a produit la divergence
constatee le 2026-08-11 : produit 1.2.0 en trois endroits, DSL annonce 1.1 par
les generateurs alors que 252 manifests portaient 1.0.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

import hydra_etl

ROOT = Path(__file__).resolve().parents[1]

# Fichier autorise a contenir un litteral de version produit.
SOURCE_OF_TRUTH = ROOT / "hydra_etl" / "__init__.py"

# Numero de version semantique complet : 1.2.0, 0.9.4...
_SEMVER = re.compile(r'["\'](\d+\.\d+\.\d+[^"\']*)["\']')

# Faux positifs : versions de dependances, de Python, de schemas JSON.
_IGNORE_CONTEXT = re.compile(
    r"python_requires|requires-python|>=|<=|==|~=|"
    r"json-schema\.org|Programming Language|draft-\d"
)


def _python_files(*dirs: str):
    for d in dirs:
        for p in (ROOT / d).rglob("*.py"):
            parts = set(p.parts)
            if parts & {"_backups", "_archive", "__pycache__", "backup"}:
                continue
            yield p


class TestSourceOfTruth:
    def test_product_version_is_a_valid_semver(self):
        assert re.fullmatch(r"\d+\.\d+\.\d+([.-]\w+)?", hydra_etl.__version__), \
            f"version produit invalide : {hydra_etl.__version__}"

    def test_dsl_version_is_separate_from_product_version(self):
        # Regle 3.2 : les deux numeros n'ont aucune raison de coincider.
        assert hydra_etl.DSL_VERSION != hydra_etl.__version__

    def test_license_is_declared(self):
        assert hydra_etl.__license__ == "AGPL-3.0-or-later"


class TestNoDuplicatedLiteral:
    def test_product_version_appears_nowhere_else(self):
        """Regle 3.1 — un seul endroit ecrit le numero, tous les autres le lisent."""
        version = hydra_etl.__version__
        offenders = []
        for path in _python_files("hydra_etl", "scripts"):
            if path == SOURCE_OF_TRUTH:
                continue
            for lineno, line in enumerate(
                path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
            ):
                if version in line and not _IGNORE_CONTEXT.search(line):
                    offenders.append(f"{path.relative_to(ROOT)}:{lineno}: {line.strip()}")
        assert not offenders, (
            "Litteral de version produit hors de hydra_etl/__init__.py :\n  "
            + "\n  ".join(offenders)
        )

    def test_dsl_version_is_never_hard_coded(self):
        """La version du DSL ne se recopie pas davantage."""
        offenders = []
        pattern = re.compile(r'DSL_VERSION\s*=\s*["\']')
        for path in _python_files("hydra_etl", "scripts"):
            if path == SOURCE_OF_TRUTH:
                continue
            for lineno, line in enumerate(
                path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
            ):
                if pattern.search(line):
                    offenders.append(f"{path.relative_to(ROOT)}:{lineno}: {line.strip()}")
        assert not offenders, (
            "DSL_VERSION redefini au lieu d'etre importe :\n  " + "\n  ".join(offenders)
        )


class TestConsumersReadTheSource:
    def test_cli_reports_the_package_version(self):
        from hydra_etl.cli.hdrctl import VERSION
        assert VERSION == hydra_etl.__version__

    def test_cli_package_reexports_without_redefining(self):
        from hydra_etl.cli import __version__ as cli_version
        assert cli_version == hydra_etl.__version__

    def test_openapi_version_follows_the_package(self):
        pytest.importorskip("fastapi", reason="extra [server] absent")
        from hydra_etl.api.main import app
        assert app.version == hydra_etl.__version__

    def test_health_endpoint_reports_both_numbers(self):
        pytest.importorskip("fastapi", reason="extra [server] absent")
        from fastapi.testclient import TestClient
        from hydra_etl.api.main import app

        payload = TestClient(app).get("/api/health").json()
        assert payload["version"] == hydra_etl.__version__
        assert payload["dsl_version"] == hydra_etl.DSL_VERSION


class TestManifestsAgreeWithTheDslVersion:
    def test_shipped_manifests_all_carry_the_declared_dsl_version(self):
        """Les manifests livres doivent porter la version du DSL courante."""
        declared = hydra_etl.DSL_VERSION
        seen: dict[str, list[str]] = {}
        for folder in ("test_scenarios", "examples"):
            base = ROOT / folder
            if not base.is_dir():
                continue
            for path in base.rglob("*.yaml"):
                if {"_backups", "_archive"} & set(path.parts):
                    continue
                for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                    m = re.match(r'^version:\s*["\']?([\d.]+)["\']?\s*$', line)
                    if m:
                        seen.setdefault(m.group(1), []).append(str(path.relative_to(ROOT)))
                        break
        assert seen, "aucun manifest trouve — le test ne verifie rien"
        assert set(seen) == {declared}, (
            f"versions de DSL trouvees dans les manifests : {sorted(seen)}, "
            f"attendu uniquement {declared!r}"
        )
