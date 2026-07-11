"""
conftest.py — Configuration pytest pour Hydra ETL.

Langues supportées : en (défaut), es.
"""
import os

# Assure que les tests tournent en anglais par défaut.
os.environ.setdefault("HYDRA_LANG", "en")
