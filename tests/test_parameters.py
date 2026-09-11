"""
Tests du résolveur de paramètres (internal/config/parameters.py).

Couvre : coercion de type, précédence multi-couches, préservation de type
(placeholder plein vs intégré), {{ env:x }}, required manquant, mode non-strict.
"""

import os

import pytest

from hydra_etl.internal.config.parameters import (
    ParameterError,
    ParameterResolver,
    build_effective,
    coerce_value,
)


# ---------------------------------------------------------------------
# Coercion
# ---------------------------------------------------------------------

def test_coerce_int():
    assert coerce_value("1000", "int", "batch") == 1000

def test_coerce_float():
    assert coerce_value("1.5", "float") == 1.5

def test_coerce_bool_variants():
    assert coerce_value("true", "bool") is True
    assert coerce_value("no", "bool") is False
    assert coerce_value(1, "bool") is True

def test_coerce_json():
    assert coerce_value('{"a": 1}', "json") == {"a": 1}

def test_coerce_invalid_raises():
    with pytest.raises(ParameterError, match="non convertible"):
        coerce_value("abc", "int", "x")


# ---------------------------------------------------------------------
# build_effective : précédence + defaults + required
# ---------------------------------------------------------------------

def test_default_used_when_no_value():
    decls = {"batch": {"type": "int", "default": 1000}}
    eff = build_effective(decls, [])
    assert eff["batch"] == 1000

def test_precedence_last_layer_wins():
    decls = {"batch": {"type": "int", "default": 1000}}
    # ordre faible -> fort : project, workflow, job, runtime
    eff = build_effective(decls, [{"batch": 500}, {"batch": 800}, {}, {"batch": 42}])
    assert eff["batch"] == 42

def test_value_coerced_to_declared_type():
    decls = {"batch": {"type": "int", "default": 0}}
    eff = build_effective(decls, [{"batch": "250"}])
    assert eff["batch"] == 250 and isinstance(eff["batch"], int)

def test_required_missing_raises():
    decls = {"schema": {"type": "string", "required": True}}
    with pytest.raises(ParameterError, match="requis manquant"):
        build_effective(decls, [])

def test_required_satisfied_by_layer():
    decls = {"schema": {"type": "string", "required": True}}
    eff = build_effective(decls, [{"schema": "staging"}])
    assert eff["schema"] == "staging"

def test_undeclared_value_passes_through():
    eff = build_effective({}, [{"adhoc": "x"}])
    assert eff["adhoc"] == "x"


# ---------------------------------------------------------------------
# Résolveur : substitution + préservation de type
# ---------------------------------------------------------------------

def test_full_placeholder_preserves_type():
    r = ParameterResolver(params={"batch": 1000})
    out = r.resolve({"extract": {"batch_size": "{{ param:batch }}"}})
    assert out["extract"]["batch_size"] == 1000
    assert isinstance(out["extract"]["batch_size"], int)

def test_embedded_placeholder_is_string():
    r = ParameterResolver(params={"schema": "staging"})
    assert r.resolve("table_{{ param:schema }}_v2") == "table_staging_v2"

def test_resolves_in_lists_and_nested():
    r = ParameterResolver(params={"a": 1, "b": 2})
    out = r.resolve({"cols": ["{{ param:a }}", "{{ param:b }}", "lit"]})
    assert out["cols"] == [1, 2, "lit"]

def test_env_placeholder(monkeypatch):
    monkeypatch.setenv("MY_HOST", "db.local")
    r = ParameterResolver(params={}, env=dict(os.environ))
    assert r.resolve("{{ env:MY_HOST }}") == "db.local"

def test_missing_param_strict_raises():
    r = ParameterResolver(params={})
    with pytest.raises(ParameterError, match="non résolu"):
        r.resolve("{{ param:nope }}")

def test_missing_param_non_strict_none():
    r = ParameterResolver(params={}, strict=False)
    assert r.resolve("{{ param:nope }}") is None

def test_non_placeholder_untouched():
    r = ParameterResolver(params={"a": 1})
    assert r.resolve("plain string") == "plain string"
    assert r.resolve(42) == 42
    assert r.resolve(True) is True
