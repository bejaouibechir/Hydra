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
