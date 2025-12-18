"""
Tests unitaires du parser transformations.yaml (MVP).

But :
- valider le schéma (structure steps)
- valider les opérations supportées et leurs paramètres
- vérifier les erreurs explicites (op inconnue, params manquants, types invalides)
- vérifier le lien CRITIQUE op -> modèle (pas de validation "accidentelle")
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from internal.parser.transform import TransformParser


def test_transform_parser_ok_minimal():
    """
    Cas OK : une suite simple de steps valides.
    """
    raw = {
        "steps": [
            {"select": {"columns": ["id", "name", "name"]}},
            {"filter": {"expr": "id > 1"}},
            {"calculate": {"column": "total", "expr": "price * qty"}},
            {"rename": {"mapping": {"name": "full_name"}}},
            {"cast": {"mapping": {"id": "int", "total": "float"}}},
        ]
    }

    cfg = TransformParser().parse(raw)

    assert len(cfg.steps) == 5
    assert cfg.steps[0].op == "select"
    assert cfg.steps[0].params.columns == ["id", "name"]  # dédupliqué
    assert cfg.steps[1].op == "filter"
    assert cfg.steps[1].params.expr == "id > 1"


def test_transform_parser_supports_wrapped_root():
    """
    Cas OK : wrapper transformations: { steps: [...] }
    """
    raw = {
        "transformations": {
            "steps": [
                {"filter": {"expr": "x > 0"}},
            ]
        }
    }

    cfg = TransformParser().parse(raw)
    assert len(cfg.steps) == 1
    assert cfg.steps[0].op == "filter"


def test_transform_parser_rejects_empty_steps():
    """
    Cas KO : steps vide.
    """
    raw = {"steps": []}
    with pytest.raises(ValidationError):
        TransformParser().parse(raw)


def test_transform_parser_rejects_steps_not_list():
    """
    Cas KO : steps doit être une liste.
    """
    raw = {"steps": {"select": {"columns": ["id"]}}}
    with pytest.raises(ValueError):
        TransformParser().parse(raw)


def test_transform_parser_rejects_step_not_one_key():
    """
    Cas KO : step doit être dict à une seule clé.
    """
    raw = {"steps": [{"select": {"columns": ["id"]}, "filter": {"expr": "id > 1"}}]}
    with pytest.raises(ValueError):
        TransformParser().parse(raw)


def test_transform_parser_rejects_unknown_op():
    """
    Cas KO : opération inconnue.
    """
    raw = {"steps": [{"unknown": {"x": 1}}]}
    with pytest.raises(ValueError):
        TransformParser().parse(raw)


def test_transform_parser_rejects_params_not_dict():
    """
    Cas KO : params d'une op doivent être un dict.
    """
    raw = {"steps": [{"filter": "id > 1"}]}
    with pytest.raises(ValueError):
        TransformParser().parse(raw)


def test_transform_parser_rejects_select_without_columns():
    """
    Cas KO : select.columns obligatoire.
    """
    raw = {"steps": [{"select": {}}]}
    with pytest.raises(ValidationError):
        TransformParser().parse(raw)


def test_transform_parser_rejects_filter_empty_expr():
    """
    Cas KO : filter.expr vide.
    """
    raw = {"steps": [{"filter": {"expr": "   "}}]}
    with pytest.raises(ValidationError):
        TransformParser().parse(raw)


def test_transform_parser_rejects_cast_invalid_type():
    """
    Cas KO : cast type non supporté.
    """
    raw = {"steps": [{"cast": {"mapping": {"id": "uuid"}}}]}
    with pytest.raises(ValidationError):
        TransformParser().parse(raw)
