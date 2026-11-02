"""
conftest.py — Configuration pytest pour Hydra ETL.

Langues supportées : en (défaut), es.
"""
import os

# Assure que les tests tournent en anglais par défaut.
os.environ.setdefault("HYDRA_LANG", "en")


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _forget_masked_secrets():
    """Le registre des secrets masqués est global au processus : chaque test
    repart d'un registre vide (un secret d'un test ne masque rien dans le suivant)."""
    from hydra_etl.internal.config import masking
    masking.clear()
    os.environ.pop(masking.VISIBILITY_ENV, None)
    yield
    masking.clear()
    os.environ.pop(masking.VISIBILITY_ENV, None)


@pytest.fixture(autouse=True)
def _isolated_hydra_home(tmp_path_factory, monkeypatch):
    """Variables globales (~/.hydra/env) : chaque test a son propre dossier,
    vide ; celles de la machine ne s'invitent jamais dans un test."""
    from hydra_etl.internal.config import loader
    monkeypatch.setenv(loader.HOME_ENV, str(tmp_path_factory.mktemp("hydra_home")))
    monkeypatch.delenv(loader.ENV_FILE_ENV, raising=False)
    monkeypatch.delenv("HYDRA_ENV", raising=False)
    yield
    loader.restore_global_env()
    for k in ("HYDRA_ENV", loader.ENV_FILE_ENV):     # posées par le CLI (--env, --env-file)
        os.environ.pop(k, None)
