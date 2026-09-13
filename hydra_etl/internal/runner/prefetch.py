"""
prefetch.py — lire le lot suivant pendant que le lot courant est transformé.

Le principe
-----------
Un job alterne strictement « lire un lot » puis « transformer et écrire ce
lot ». Pendant la lecture, pandas ne fait rien ; pendant la transformation,
le disque ne fait rien. Un thread de lecture avec une file bornée fait se
recouvrir les deux : on masque le plus petit des deux temps.

Tout dépend de ce que la lecture relâche comme GIL — et la mesure est
nette (300k lignes, 2 cœurs, médiane de 5) :

    lecteur CSV Rust     S1 1,52 -> 1,29 s (x1,18)   S3 0,89 -> 0,78 s (x1,14)
    lecteur CSV Python   S1 3,52 -> 3,24 s (bruit)   S3 1,90 -> 2,10 s (x0,90)

Le lecteur Rust relâche le GIL pendant l'analyse du fichier : le
recouvrement est réel. Le lecteur Python le garde : les deux threads se
disputent le même processeur logique et le thread ne fait qu'ajouter du
surcoût. Le préchargement est donc actif **par défaut seulement quand le
lecteur relâche le GIL** (`reader_releases_gil()` du connecteur), et
forçable dans les deux sens par HYDRA_PREFETCH.

Garanties
---------
- L'ordre des lots est strictement conservé.
- Une exception levée par la source est transmise telle quelle au
  consommateur : mêmes messages d'erreur qu'avant.
- Si le consommateur s'arrête avant la fin, le thread est arrêté et le
  générateur source refermé proprement.

Réglages : HYDRA_PREFETCH=0 force l'arrêt, HYDRA_PREFETCH=1 force la
marche, non défini = automatique. HYDRA_PREFETCH_SIZE (défaut 1) donne la
profondeur de la file.
"""

from __future__ import annotations

import logging
import os
import queue
import threading
from typing import Any, Iterable, Iterator

logger = logging.getLogger(__name__)

_OFF = {"0", "false", "no", "off"}
_ON = {"1", "true", "yes", "on"}
_END = object()


def prefetch_enabled() -> bool | None:
    """True/False si HYDRA_PREFETCH tranche, None si c'est automatique."""
    raw = os.environ.get("HYDRA_PREFETCH", "").strip().lower()
    if raw in _OFF:
        return False
    if raw in _ON:
        return True
    return None


def should_prefetch(connector: Any, table: Any = None) -> bool:
    """Précharger ? Oui si le lecteur relâche le GIL, sauf consigne contraire."""
    forced = prefetch_enabled()
    if forced is not None:
        return forced
    releases = getattr(connector, "reader_releases_gil", None)
    if not callable(releases):
        return False
    try:
        return bool(releases(table))
    except Exception:  # noqa: BLE001 - jamais bloquant
        return False


def prefetch_size() -> int:
    raw = os.environ.get("HYDRA_PREFETCH_SIZE", "").strip()
    if raw:
        try:
            return max(1, min(8, int(raw)))
        except ValueError:
            pass
    return 1


def prefetch(source: Iterable[Any], *, enabled: bool | None = None,
             size: int | None = None) -> Iterator[Any]:
    """Itère `source` en la faisant avancer d'un lot dans un thread dédié."""
    if enabled is None:
        enabled = bool(prefetch_enabled())
    if not enabled:
        yield from source
        return

    depth = size if size is not None else prefetch_size()
    box: "queue.Queue[Any]" = queue.Queue(maxsize=depth)
    stop = threading.Event()
    failure: list = []

    iterator = iter(source)

    def lire() -> None:
        try:
            for item in iterator:
                if stop.is_set():
                    break
                # timeout : sans lui, un consommateur arrêté bloquerait ce
                # thread indéfiniment sur une file pleine.
                while not stop.is_set():
                    try:
                        box.put(item, timeout=0.2)
                        break
                    except queue.Full:
                        continue
        except BaseException as exc:  # noqa: BLE001 - retransmise telle quelle
            failure.append(exc)
        finally:
            try:
                box.put(_END, timeout=5)
            except queue.Full:
                pass

    thread = threading.Thread(target=lire, name="hydra-prefetch", daemon=True)
    thread.start()

    try:
        while True:
            item = box.get()
            if item is _END:
                break
            yield item
        if failure:
            raise failure[0]
    finally:
        stop.set()
        # vider la file pour débloquer le thread s'il attendait d'y déposer
        while True:
            try:
                box.get_nowait()
            except queue.Empty:
                break
        thread.join(timeout=5)
        closer = getattr(iterator, "close", None)
        if callable(closer):
            try:
                closer()
            except Exception:  # noqa: BLE001
                pass
