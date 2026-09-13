"""
batch_size.py — choisir la taille des lots en mémoire plutôt qu'en lignes.

Pourquoi
--------
`batch_size` se déclare en nombre de lignes, mais ce qui compte est la
mémoire d'un lot. Une même valeur donne 2 Mo sur une table étroite et
600 Mo sur une table large. Et le surcoût fixe de pandas par lot est tel
qu'un lot trop petit est catastrophique : le profilage d'Hydra mesure
**×2 à ×20 plus lent** entre `batch_size: 100` et `batch_size: 10 000`
selon le scénario.

Ce que fait ce module
---------------------
- Quand `batch_size` **n'est pas déclaré** dans le YAML, la taille est
  calculée pour viser ~16 Mo par lot, à partir d'un échantillon réel de
  la source. Cette cible vient de la mesure : sur le scénario S1,
  l'optimum se situe entre 10 000 et 25 000 lignes (~6 à 14 Mo) ; en
  dessous le surcoût par lot domine, au-dessus les gros lots redeviennent
  plus lents. Les jobs qui déclarent une valeur la gardent : rien ne
  change pour eux.
- Quand une valeur déclarée est manifestement trop petite, un
  avertissement le dit une fois, avec l'ordre de grandeur du coût.
- Si la source ne sait pas s'estimer (base de données, API...), on garde
  la valeur par défaut historique de 10 000 lignes.

Réglages : HYDRA_BATCH_TARGET_BYTES (défaut 16777216), HYDRA_BATCH_AUTO=0
pour revenir au 10 000 fixe.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

_OFF = {"0", "false", "no", "off"}

DEFAULT_ROWS = 10_000          # valeur historique, conservée en repli
MIN_ROWS = 1_000               # en dessous, le surcoût par lot domine
MAX_ROWS = 50_000              # au-delà, les gros lots redeviennent plus lents
SMALL_BATCH_WARNING = 1_000    # seuil d'avertissement


def auto_enabled() -> bool:
    return os.environ.get("HYDRA_BATCH_AUTO", "1").strip().lower() not in _OFF


def target_bytes() -> int:
    raw = os.environ.get("HYDRA_BATCH_TARGET_BYTES", "").strip()
    if raw:
        try:
            value = int(raw)
            if value > 0:
                return value
        except ValueError:
            pass
    return 16 * 1024 * 1024


def warn_if_too_small(batch_size: int, job_id: str = "") -> None:
    """Avertit une fois quand un batch_size déclaré est trop petit."""
    if batch_size >= SMALL_BATCH_WARNING:
        return
    logger.warning(
        "Job '%s': batch_size=%d est très petit. Le surcoût fixe de pandas par "
        "lot domine alors le temps du job (mesuré : jusqu'à x20 plus lent qu'à "
        "10 000). Retirez batch_size pour le laisser se régler tout seul, ou "
        "mettez au moins %d.",
        job_id, batch_size, SMALL_BATCH_WARNING,
    )


def resolve(connector: Any, table: Optional[str], job_id: str = "") -> int:
    """Nombre de lignes par lot visant ~64 Mo, ou la valeur par défaut."""
    if not auto_enabled():
        return DEFAULT_ROWS

    estimate = getattr(connector, "estimate_row_bytes", None)
    if not callable(estimate):
        return DEFAULT_ROWS
    try:
        per_row = estimate(table)
    except Exception as exc:  # noqa: BLE001 - jamais bloquant
        logger.debug("Estimation de la taille de ligne impossible : %s", exc)
        return DEFAULT_ROWS

    if not per_row or per_row <= 0:
        return DEFAULT_ROWS

    rows = int(target_bytes() / float(per_row))
    rows = max(MIN_ROWS, min(MAX_ROWS, rows))
    logger.info(
        "Job '%s': batch_size automatique = %d lignes (~%.0f o/ligne, cible %.0f Mo)",
        job_id, rows, per_row, target_bytes() / 1024 / 1024,
    )
    return rows
