"""
internal/dsl_version.py — Lecture tolérante du champ `version` des manifestes.

Le champ `version:` en tête de chaque manifeste est la version du **format**
du DSL, pas celle de Hydra (Règle 3.2 de CLAUDE.md). Jusqu'ici aucun parseur
ne le lisait : un manifeste portant `version: "42.7"` était accepté sans un
mot, ce qui rendait intenable la promesse de la règle — « le jour d'une
rupture, le moteur doit lire l'ancienne et la nouvelle version ».

Ce module lève la contradiction sans rien casser. Il **lit** le champ et
**avertit**, mais ne refuse jamais un manifeste :

    absent                -> silence, on suppose la version courante
    égal à DSL_VERSION    -> silence
    plus ancien           -> avertissement, lecture poursuivie
    plus récent           -> avertissement, lecture poursuivie
    illisible             -> avertissement, lecture poursuivie

Refuser serait une rupture de contrat au sens SemVer, donc réservé à une
version MAJEURE. Avertir suffit à informer l'utilisateur aujourd'hui, et donne
au moteur le point d'accroche dont il aura besoin le jour d'une v2 du DSL.

Les messages sont en anglais : ils atteignent l'utilisateur (Règle −2).
"""
from __future__ import annotations

import logging
from typing import Any, Mapping, Optional, Tuple

from hydra_etl import DSL_VERSION

logger = logging.getLogger(__name__)

__all__ = ["check_dsl_version", "parse_version", "DSL_VERSION"]


def parse_version(raw: Any) -> Optional[Tuple[int, ...]]:
    """Convertit "1.0" en (1, 0). Retourne None si ce n'est pas un numéro."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        return tuple(int(part) for part in text.split("."))
    except ValueError:
        return None


def check_dsl_version(data: Mapping[str, Any], source: Any = None) -> Optional[str]:
    """Contrôle le champ `version` d'un manifeste déjà chargé.

    Retourne la version déclarée, ou None si le champ est absent. N'échoue
    jamais : la valeur de retour et le journal sont les seuls effets.
    """
    if not isinstance(data, Mapping):
        return None

    declared = data.get("version")
    if declared is None:
        return None

    declared_text = str(declared).strip()
    if declared_text == DSL_VERSION:
        return declared_text

    where = f" in {source}" if source else ""
    found = parse_version(declared_text)
    expected = parse_version(DSL_VERSION)

    if found is None:
        logger.warning(
            "Unrecognized DSL version %r%s. Hydra reads this manifest as DSL %s. "
            "The `version` field should hold a number such as \"%s\".",
            declared_text, where, DSL_VERSION, DSL_VERSION,
        )
    elif expected is not None and found > expected:
        logger.warning(
            "Manifest%s declares DSL version %s, which is newer than the %s this "
            "engine implements. Reading it anyway — upgrade Hydra if something "
            "looks wrong.",
            where, declared_text, DSL_VERSION,
        )
    else:
        logger.warning(
            "Manifest%s declares DSL version %s, older than the current %s. "
            "Reading it anyway — the format is backward compatible.",
            where, declared_text, DSL_VERSION,
        )

    return declared_text
