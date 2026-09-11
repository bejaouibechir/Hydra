from __future__ import annotations

import os
import pytest

from hydra_etl.internal.config.secrets import SecretResolver, SecretResolutionError


def test_resolve_env_placeholder(monkeypatch):
    """
    Vérifie ${ENV:VAR} -> valeur env.
    """
    monkeypatch.setenv("DB_HOST", "127.0.0.1")

    r = SecretResolver(secrets={})
    data = {"host": "${ENV:DB_HOST}"}

    resolved = r.resolve(data)
    assert resolved["host"] == "127.0.0.1"


def test_resolve_secret_placeholder():
    """
    Vérifie ${SECRET:KEY} -> valeur secrets dict.
    """
    r = SecretResolver(secrets={"db.password": "p@ss"})
    data = {"password": "${SECRET:db.password}"}

    resolved = r.resolve(data)
    assert resolved["password"] == "p@ss"


def test_resolve_nested_and_embedded_placeholders(monkeypatch):
    """
    Vérifie :
    - récursivité (dict/list)
    - placeholders intégrés dans une chaîne
    """
    monkeypatch.setenv("DB_HOST", "localhost")

    r = SecretResolver(secrets={"db.password": "secret123"})
    data = {
        "url": "mysql://${ENV:DB_HOST}:3306",
        "auth": {"pwd": "${SECRET:db.password}"},
        "items": ["x", "${ENV:DB_HOST}"],
    }

    resolved = r.resolve(data)
    assert resolved["url"] == "mysql://localhost:3306"
    assert resolved["auth"]["pwd"] == "secret123"
    assert resolved["items"][1] == "localhost"


def test_missing_env_raises(monkeypatch):
    """
    Une variable manquante doit lever une erreur claire.
    """
    monkeypatch.delenv("MISSING_ENV", raising=False)

    r = SecretResolver(secrets={})
    with pytest.raises(SecretResolutionError):
        r.resolve({"x": "${ENV:MISSING_ENV}"})


def test_missing_secret_raises():
    """
    Un secret manquant doit lever une erreur claire.
    """
    r = SecretResolver(secrets={})
    with pytest.raises(SecretResolutionError):
        r.resolve({"x": "${SECRET:not.found}"})
