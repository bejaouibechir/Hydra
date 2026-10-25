"""
Chargement d'une destination par un job : begin → stage → publish | abort.

Un job ouvre UNE session de chargement (`Connector.begin_load`) ; chaque lot
de sortie y est déposé (`stage`) ; à la fin, `publish()` rend le résultat
visible ; en cas d'échec ou d'interruption (Ctrl+C), `abort()` annule.

En **tout ou rien** (`atomic=True`), rien n'est visible avant `publish()` et
`abort()` laisse la destination comme avant le job :
- bases (PostgreSQL, MySQL/MariaDB, SQL Server) : une seule transaction ;
  `replace` = TRUNCATE (PostgreSQL, SQL Server : annulable) ou DELETE (MySQL,
  table transactionnelle InnoDB) dans cette transaction ;
- fichiers CSV / Parquet : `replace` = fichier temporaire du même dossier puis
  remplacement (`os.replace`) ; `append` CSV = retour à la taille d'origine.
Sans tout ou rien, chaque lot est validé dès qu'il est écrit (comportement
historique) : un échec laisse les lots déjà écrits.

Capacités déclarées par chaque connecteur (attributs de classe) :
- `atomic_load_modes`    : modes qu'il sait publier en tout ou rien ;
- `atomic_default_modes` : modes en tout ou rien par défaut (sans surcoût).
`load.atomic` (destinations.yaml) force le choix ; demander le tout ou rien à
un connecteur qui ne sait pas le faire est une erreur, jamais une dégradation
silencieuse.

Deux jobs du même processus qui écrivent la même destination ne se
chevauchent pas : un verrou par destination est tenu de begin à publish/abort.
"""
from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

logger = logging.getLogger(__name__)

ATOMIC_MODES_ALL: FrozenSet[str] = frozenset({"append", "replace", "upsert"})


class AtomicLoadError(ValueError):
    """Tout ou rien demandé (`load.atomic: true`) mais impossible ici."""


# ── Verrous par destination (même processus) ───────────────────────────────
_LOCKS: Dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def _lock_for(target: str) -> threading.Lock:
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(target, threading.Lock())


# ── Session ────────────────────────────────────────────────────────────────
class LoadSession:
    """Chargement d'une destination par un job.

    Sous-classes : `_stage(batch)`, `_publish()`, `_abort()`. La classe de
    base compte les lots, tient le verrou de la destination et garantit
    qu'une session n'est terminée qu'une fois."""

    def __init__(self, *, target: str, table: str, mode: str, atomic: bool) -> None:
        self.target = target
        self.table = table
        self.mode = mode
        self.atomic = atomic
        self.rows_staged = 0
        self.batches_committed = 0        # lots déjà visibles (sans tout ou rien)
        self.state = "open"               # open | published | aborted
        self._lock = _lock_for(target)
        if not self._lock.acquire(blocking=False):
            logger.info("Waiting for another job writing to %s", target)
            self._lock.acquire()
        self._held = True

    # contrat
    def stage(self, batch: Any) -> None:
        if self.state != "open":
            raise RuntimeError(f"load session already {self.state}")
        if batch is None or len(batch) == 0:
            return
        self._stage(batch)
        self.rows_staged += len(batch)
        if not self.atomic:
            self.batches_committed += 1

    def publish(self) -> None:
        if self.state != "open":
            return
        try:
            self._publish()
            self.state = "published"
        finally:
            if self.state != "published":
                self.abort()          # libère aussi le verrou
            else:
                self._release()

    def abort(self) -> None:
        if self.state != "open":
            return
        self.state = "aborted"
        try:
            self._abort()
        except Exception as e:  # noqa: BLE001 — ne pas masquer l'erreur d'origine
            logger.warning("Load abort of %s failed: %s", self.target, e)
        finally:
            self._release()

    @property
    def partial_write(self) -> bool:
        """True si un échec a laissé des lignes écrites dans la destination."""
        return self.state != "published" and not self.atomic and self.batches_committed > 0

    # à fournir
    def _stage(self, batch: Any) -> None:
        raise NotImplementedError

    def _publish(self) -> None:
        pass

    def _abort(self) -> None:
        pass

    def _release(self) -> None:
        if self._held:
            self._held = False
            self._lock.release()


class LegacyLoadSession(LoadSession):
    """Connecteur sans session propre : un appel à load_batches() par lot
    (replace au premier lot, append ensuite). Jamais en tout ou rien."""

    def __init__(self, connector: Any, *, table: str, mode: str, key: Optional[List[str]]) -> None:
        name = getattr(connector, "name", "?")
        super().__init__(target=f"{type(connector).__name__}:{name}:{table}", table=table,
                         mode=mode, atomic=False)
        self._connector = connector
        self._key = key
        self._next_mode = mode

    def _stage(self, batch: Any) -> None:
        self._connector.load_batches([batch], table=self.table, mode=self._next_mode,
                                     key=self._key if self.mode == "upsert" else None)
        if self._next_mode == "replace":
            self._next_mode = "append"


# ── Choix du tout ou rien ──────────────────────────────────────────────────
def resolve_atomic(connector: Any, mode: str, requested: Optional[bool]) -> Tuple[bool, Optional[str]]:
    """(tout ou rien ?, remarque à journaliser).

    requested : `load.atomic` (None = défaut du connecteur pour ce mode)."""
    supported = frozenset(getattr(connector, "atomic_load_modes", frozenset()) or ())
    defaults = frozenset(getattr(connector, "atomic_default_modes", frozenset()) or ())
    kind = getattr(connector, "name", None) or type(connector).__name__
    if requested is True:
        if mode not in supported:
            raise AtomicLoadError(
                f"destination '{kind}': all-or-nothing load (atomic: true) is not available "
                f"for mode '{mode}' with {type(connector).__name__}"
                + (f" (available for: {', '.join(sorted(supported))})" if supported else "")
                + ". Remove 'atomic: true' or change the mode.")
        return True, None
    if requested is False:
        return False, None
    if mode in defaults and mode in supported:
        return True, None
    if mode == "replace":
        return False, (f"destination '{kind}': {type(connector).__name__} cannot replace in "
                       f"all-or-nothing; a failure can leave the destination partly written")
    return False, None


def open_load_session(connector: Any, *, table: str, mode: str, key: Optional[List[str]],
                      atomic: bool) -> LoadSession:
    """Session de chargement du connecteur, ou chargement lot par lot s'il n'en a pas."""
    begin = getattr(connector, "begin_load", None)
    if callable(begin):
        return begin(table=table, mode=mode, key=key, atomic=atomic)
    if atomic:
        raise AtomicLoadError(f"{type(connector).__name__}: all-or-nothing load is not available")
    return LegacyLoadSession(connector, table=table, mode=mode, key=key)


# ── Fichiers : temporaire du même dossier, orphelins ────────────────────────
_TMP_MARK = ".hydra-tmp-"


def temp_path_for(target: Path) -> Path:
    """Fichier temporaire à côté de la cible (même disque : remplacement instantané).
    Le PID permet de reconnaître les orphelins d'un processus mort."""
    return target.with_name(f".{target.name}{_TMP_MARK}{os.getpid()}-{uuid.uuid4().hex[:8]}")


def _pid_alive(pid: int) -> Optional[bool]:
    try:
        import psutil  # type: ignore
        return bool(psutil.pid_exists(pid))
    except ImportError:
        pass
    if os.name == "posix":
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True
    return None                      # inconnu (Windows sans psutil)


def cleanup_orphans(target: Path, max_age_s: float = 24 * 3600) -> List[Path]:
    """Supprime les temporaires laissés par un processus arrêté (crash, kill)
    pour cette cible. Sans moyen de le savoir, seulement ceux de plus de 24 h."""
    removed: List[Path] = []
    prefix = f".{target.name}{_TMP_MARK}"
    try:
        candidates = list(target.parent.glob(prefix + "*"))
    except OSError:
        return removed
    now = time.time()
    for p in candidates:
        try:
            pid = int(p.name[len(prefix):].split("-", 1)[0])
        except ValueError:
            continue
        if pid == os.getpid():
            continue
        alive = _pid_alive(pid)
        try:
            old = now - p.stat().st_mtime > max_age_s
        except OSError:
            continue
        if alive is False or (alive is None and old):
            try:
                p.unlink()
                removed.append(p)
                logger.info("Removed an orphan temporary file: %s", p)
            except OSError:
                pass
    return removed


def replace_file(tmp: Path, target: Path, retries: int = 5, wait_s: float = 0.4) -> None:
    """os.replace avec quelques essais (Windows : fichier ouvert par Excel...)."""
    for i in range(retries):
        try:
            os.replace(tmp, target)
            return
        except PermissionError as e:
            if i == retries - 1:
                raise ValueError(
                    f"cannot replace {target}: the file is in use by another program "
                    f"(close it and run again). The previous content is kept. ({e})") from e
            time.sleep(wait_s)
