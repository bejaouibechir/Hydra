"""Non-régression de `hdrctl validate --strict`.

1. Les étapes sont reconnues quelle que soit la forme du fichier
   (`steps:` à la racine ou `transformations: steps:`).
2. Les expressions filter/calculate sont analysées sans être évaluées :
   une erreur de syntaxe fait échouer la validation (code 1), une
   expression valide — y compris la syntaxe propre à pandas — passe.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from click.testing import CliRunner

from hydra_etl.cli.hdrctl import cli, _check_expr_syntax

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def runner():
    return CliRunner(env={"HYDRA_LANG": "en"})


def _job(tmp_path: Path, transformations: str) -> Path:
    job = tmp_path / "job"
    job.mkdir()
    (job / "sources.yaml").write_text(
        "sources:\n  src:\n    type: csv\n    extract:\n      table: in.csv\n", encoding="utf-8")
    (job / "destinations.yaml").write_text(
        "destinations:\n  dst:\n    type: csv\n    load:\n      table: out.csv\n      mode: replace\n",
        encoding="utf-8")
    (job / "pipeline.yaml").write_text("pipeline:\n  from: src\n  to: dst\n", encoding="utf-8")
    (job / "transformations.yaml").write_text(transformations, encoding="utf-8")
    return job


ROOT_FORM = "steps:\n  - filter:\n      expr: 'price > 0'\n  - calculate:\n      column: total\n      expr: 'price * qty'\n"
NESTED_FORM = "transformations:\n" + "".join("  " + line + "\n" for line in ROOT_FORM.splitlines())


@pytest.mark.parametrize("content", [ROOT_FORM, NESTED_FORM], ids=["root", "nested"])
def test_strict_recognizes_steps_in_both_forms(runner, tmp_path, content):
    result = runner.invoke(cli, ["validate", str(_job(tmp_path, content)), "--strict"])
    assert result.exit_code == 0, result.output
    assert "filter, calculate" in result.output
    assert "calculate.total" in result.output


def test_strict_on_repository_example(runner):
    result = runner.invoke(cli, ["validate", str(ROOT / "examples" / "minimal_csv"), "--strict"])
    assert result.exit_code == 0, result.output
    assert "cast, filter, calculate, rename" in result.output


@pytest.mark.parametrize("bad", ["price * (qty", "price >", "price ^> 0", "(a ?? 0)"])
def test_strict_rejects_invalid_expression(runner, tmp_path, bad):
    content = f"steps:\n  - calculate:\n      column: total\n      expr: \"{bad}\"\n"
    result = runner.invoke(cli, ["validate", str(_job(tmp_path, content)), "--strict"])
    assert result.exit_code == 1, result.output
    assert "Step 1 (calculate)" in result.output


def test_non_strict_behaviour_unchanged(runner, tmp_path):
    """Sans --strict, les expressions ne sont pas analysées (comportement historique)."""
    content = "steps:\n  - filter:\n      expr: 'price * (qty'\n"
    result = runner.invoke(cli, ["validate", str(_job(tmp_path, content))])
    assert result.exit_code == 0, result.output


# Expressions acceptées par pandas à l'exécution : jamais de fausse alerte.
VALID = [
    "price > 0",
    "price * qty",
    "`unit price` > 0 & qty < 5",
    "a > 1 and b < 2",
    "a > 1 or not b",
    "country in ['FR', 'TN']",
    "name == 'x' | code != 'y'",
    "(price - discount) / qty",
]


@pytest.mark.parametrize("expr", VALID)
def test_valid_expressions_pass_and_really_run_in_pandas(expr):
    assert _check_expr_syntax(expr) is None
    df = pd.DataFrame({"price": [1.0], "qty": [2], "unit price": [1.0], "a": [2], "b": [1],
                       "country": ["TN"], "name": ["x"], "code": ["y"], "discount": [0.0]})
    df.eval(expr, engine="python")  # la même grammaire que le moteur Hydra ETL


@pytest.mark.parametrize("expr", ["price * (qty", "price >", "price ^> 0", "(a ?? 0)", "price **"])
def test_invalid_expressions_fail_in_pandas_too(expr):
    assert _check_expr_syntax(expr) is not None
    df = pd.DataFrame({"price": [1.0], "qty": [2], "a": [1]})
    with pytest.raises(Exception):
        df.eval(expr, engine="python")
