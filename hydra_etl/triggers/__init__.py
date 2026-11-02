"""Déclencheurs de projet (Hydra 0.19) : triggers.yaml à la racine d'un projet.

Un déclencheur lance le projet (son thread.yaml, ou les `workflows` listés) quand
son événement survient : heure (cron), intervalle, fichier, fichier témoin,
changement d'une source, webhook, fin d'un autre projet — ou à la main
(`hdrctl trigger fire`). Le moteur tourne dans `hdrctl watch` et `hdrctl serve`.
"""
from hydra_etl.triggers.models import (  # noqa: F401
    TRIGGER_TYPES, ProjectTrigger, TriggerFile, TriggerFileError, load_triggers, triggers_file,
)
