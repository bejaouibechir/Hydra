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


def test_secret_falls_back_to_normalised_env_var(monkeypatch):
    """
    ${SECRET:db.password} doit lire la variable d'environnement DB_PASSWORD
    quand aucun mapping de secrets n'est injecte (cas de la CLI).
    """
    monkeypatch.setenv("DB_PASSWORD", "from-env")

    r = SecretResolver(secrets={})
    assert r.resolve({"x": "${SECRET:db.password}"})["x"] == "from-env"


def test_secret_reads_uppercase_key_from_env(monkeypatch):
    """
    La forme documentee dans le README, ${SECRET:DB_PASSWORD}, doit fonctionner
    telle quelle depuis l'environnement.
    """
    monkeypatch.setenv("DB_PASSWORD", "readme-form")

    r = SecretResolver(secrets={})
    assert r.resolve({"x": "${SECRET:DB_PASSWORD}"})["x"] == "readme-form"


def test_secret_dash_is_normalised_too(monkeypatch):
    """
    'api-token' et 'api.token' visent tous deux API_TOKEN.
    """
    monkeypatch.setenv("API_TOKEN", "t0ken")

    r = SecretResolver(secrets={})
    assert r.resolve({"x": "${SECRET:api-token}"})["x"] == "t0ken"
    assert r.resolve({"x": "${SECRET:api.token}"})["x"] == "t0ken"


def test_injected_secret_wins_over_env(monkeypatch):
    """
    Le mapping injecte (Vault, coffre applicatif) a la priorite sur l'environnement.
    """
    monkeypatch.setenv("DB_PASSWORD", "from-env")

    r = SecretResolver(secrets={"db.password": "from-vault"})
    assert r.resolve({"x": "${SECRET:db.password}"})["x"] == "from-vault"


def test_missing_secret_still_raises_when_env_is_empty(monkeypatch):
    """
    Le repli ne doit pas masquer un secret reellement absent.
    """
    monkeypatch.delenv("NOT_FOUND", raising=False)
    monkeypatch.delenv("not.found", raising=False)

    r = SecretResolver(secrets={})
    with pytest.raises(SecretResolutionError):
        r.resolve({"x": "${SECRET:not.found}"})


def test_missing_secret_message_names_the_env_var(monkeypatch):
    """
    Le message doit dire quelle variable d'environnement definir.
    """
    monkeypatch.delenv("DB_PASSWORD", raising=False)

    r = SecretResolver(secrets={})
    with pytest.raises(SecretResolutionError) as exc:
        r.resolve({"x": "${SECRET:db.password}"})
    assert "DB_PASSWORD" in str(exc.value)
