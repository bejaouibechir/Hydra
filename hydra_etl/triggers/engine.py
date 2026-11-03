"""Moteur des déclencheurs : surveille les projets et lance ceux dont l'événement arrive.

Un seul moteur pour `hdrctl watch` (sans Studio) et, plus tard, `hdrctl serve`.
Types surveillés : `cron`, `interval` (temps), `file`, `marker` (fichiers),
`source_change` (données), `after_project` (fin d'un autre projet). `webhook`
est appelé par l'API de `hdrctl serve` ; `hdrctl trigger fire` lance tout type.

Fin d'un autre projet : chaque run de projet (CLI, Studio, déclencheur, step
type: project) est noté dans <projet>/.hydra/triggers/ends.jsonl ; le moteur
relit ce fichier toutes les 5 s. Les fins antérieures au démarrage sont
ignorées ; les fins arrivées pendant un run du projet suivi donnent un seul run
de plus (la plus récente est transmise : `trigger.project`, `trigger.status`).

Données : la source est mesurée toutes les `every` (défaut 1m) dans un thread à
part (une base lente ne bloque pas le moteur). La première mesure sert de
référence ; une mesure différente lance un run avec `trigger.value` et
`trigger.previous`. Une mesure en échec est signalée et la référence est gardée.

Fichiers : le dossier est scruté toutes les `every` (défaut 5s). Les fichiers
arrivés ensemble lancent un seul run, qui reçoit les paramètres
`trigger.file` (le premier) et `trigger.files` (tous, séparés par des virgules).
Un événement de fichier n'est jamais perdu : arrivé pendant un run, il attend
la fin de ce run. Un fichier témoin (`marker`) est retiré avant le lancement
(`consume: false` pour le garder).

- Une boucle (thread) se réveille chaque seconde, relit triggers.yaml s'il a
  changé, et lance chaque déclencheur échu dans son propre thread
  (`core.fire` : sous-processus, verrou .hydra/run.lock, overlap, timeout, retry).
- Un déclencheur encore en cours dans ce moteur n'est pas relancé : l'échéance
  est notée `skipped` dans l'historique.
- Pas de rattrapage : une échéance manquée pendant un arrêt n'est pas rejouée.
- `stop()` n'accepte plus de lancement et attend la fin des runs en cours.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from hydra_etl.triggers.core import FireResult, check_triggers, fire, record
from hydra_etl.triggers.files import FileWatcher, source_for
from hydra_etl.triggers.models import ProjectTrigger, TriggerFileError, load_triggers, triggers_file

log = logging.getLogger("hydra.triggers.engine")

HANDLED = ("cron", "interval", "file", "marker", "source_change", "after_project")
FILE_TYPES = ("file", "marker")
DEFAULT_POLL = 5.0          # secondes entre deux scrutations d'un dossier
DEFAULT_DEBOUNCE = 2.0      # un fichier doit être stable 2 s avant d'être pris
DEFAULT_SOURCE_POLL = 60.0  # secondes entre deux mesures d'une source
Event = Dict[str, Any]


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Watched:
    """Un déclencheur suivi : prochaine échéance, run en cours."""
    trigger: ProjectTrigger
    next_at: Optional[datetime] = None
    running: bool = False
    note: Optional[str] = None             # pourquoi il n'est pas planifié
    watcher: Optional[FileWatcher] = None  # file / marker
    next_poll: Optional[datetime] = None
    pending: List[str] = field(default_factory=list)   # fichiers en attente d'un run
    # source_change
    value: Optional[str] = None            # dernière mesure (référence)
    measuring: bool = False
    measured: Optional[tuple] = None       # (valeur, erreur) rendu par le thread de mesure
    change: Optional[tuple] = None         # (avant, après) en attente d'un run
    # after_project
    target: Optional[Path] = None          # projet dont la fin est attendue
    seen_ts: float = 0.0                   # dernière fin lue
    ends_mtime: Optional[tuple] = None
    end: Optional[Dict[str, Any]] = None   # fin en attente d'un run


@dataclass
class ProjectState:
    root: Path
    name: str
    mtime: Optional[float] = None
    watched: Dict[str, Watched] = field(default_factory=dict)
    error: Optional[str] = None


def _project_name(root: Path) -> str:
    from hydra_etl.workflow.subprojects import _project_name as name
    return name(root)


def _poll_every(t: ProjectTrigger) -> float:
    from hydra_etl.workflow.thread import parse_delay
    if t.every is not None:
        return parse_delay(t.every)
    return DEFAULT_SOURCE_POLL if t.type == "source_change" else DEFAULT_POLL


def make_watcher(root: Path, t: ProjectTrigger) -> FileWatcher:
    from hydra_etl.workflow.thread import parse_delay
    if t.type == "marker":
        w = FileWatcher(source_for(root), t.path, ["added"], 0.0)
    else:
        deb = parse_delay(t.debounce) if t.debounce is not None else DEFAULT_DEBOUNCE
        w = FileWatcher(source_for(root), t.path, t.events_effective, deb)
    w.baseline()
    return w


def next_time(t: ProjectTrigger, after: datetime) -> Optional[datetime]:
    """Prochaine échéance d'un déclencheur de temps (None pour les autres)."""
    if t.type == "cron":
        from hydra_etl.triggers.cron import next_run
        return next_run(t.cron, after, t.timezone).astimezone(timezone.utc)
    if t.type == "interval":
        from hydra_etl.workflow.thread import parse_delay
        return after + timedelta(seconds=parse_delay(t.every))
    return None


class TriggerEngine:
    """Surveille un ou plusieurs projets.

    on_event(evt) reçoit : {"kind": "loaded" | "error" | "started" | "finished" | "skipped" |
    "stopping", "project", "trigger", ...}. `fire_fn` et `clock` sont remplaçables (tests)."""

    def __init__(self, *, env: Optional[str] = None, origin: str = "watch",
                 on_event: Optional[Callable[[Event], None]] = None,
                 fire_fn: Callable[..., FireResult] = fire,
                 measure_fn: Optional[Callable[..., str]] = None,
                 clock: Callable[[], datetime] = _now, tick: float = 1.0):
        self.env = env
        self.origin = origin
        self.on_event = on_event or (lambda e: None)
        self.fire_fn = fire_fn
        if measure_fn is None:
            from hydra_etl.triggers.sources import measure as measure_fn
        self.measure_fn = measure_fn
        self.clock = clock
        self.tick_seconds = tick
        self.projects: Dict[Path, ProjectState] = {}
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._runs: List[threading.Thread] = []

    # ── projets ────────────────────────────────────────────────────────────

    def add_project(self, root: Path) -> ProjectState:
        root = Path(root).resolve()
        with self._lock:
            st = self.projects.get(root) or ProjectState(root, _project_name(root))
            self.projects[root] = st
            self._load(st, self.clock())
            return st

    def remove_project(self, root: Path) -> None:
        with self._lock:
            self.projects.pop(Path(root).resolve(), None)

    def _emit(self, **evt: Any) -> None:
        try:
            self.on_event(evt)
        except Exception:  # noqa: BLE001  l'affichage ne doit jamais arrêter le moteur
            log.exception("trigger event handler failed")

    def _mtime(self, root: Path) -> Optional[float]:
        try:
            return triggers_file(root).stat().st_mtime
        except OSError:
            return None

    def _load(self, st: ProjectState, now: datetime) -> None:
        """(Re)lit triggers.yaml. Fichier invalide : on garde les déclencheurs précédents."""
        st.mtime = self._mtime(st.root)
        try:
            tf = load_triggers(st.root)
            check = check_triggers(st.root, tf)
        except TriggerFileError as e:
            st.error = "; ".join(e.errors)
            self._emit(kind="error", project=st.name, error=st.error,
                       kept=[n for n in st.watched])
            return
        st.error = None
        bad = {}
        for e in check.errors:
            for t in tf.triggers:
                if e.startswith(f"trigger '{t.name}'"):
                    bad.setdefault(t.name, e)
        loop = next((e for e in check.errors if e.startswith("after_project loop")), None)
        old = st.watched
        st.watched = {}
        for t in tf.triggers:
            w = Watched(t)
            prev = old.get(t.name)
            if prev is not None:
                w.running = prev.running
            if not t.enabled:
                w.note = "disabled (enabled: false)"
            elif t.name in bad:
                w.note = bad[t.name]
            elif loop and t.type == "after_project":
                w.note = loop
            elif t.type == "webhook":
                w.note = (f"type webhook: called through hdrctl serve — "
                          f"POST /api/projects/<id>/triggers/{t.name}/webhook")
            elif t.type not in HANDLED:
                w.note = f"type {t.type}: not watched yet by this version — run it with hdrctl trigger fire"
            else:
                # Même déclencheur, même réglage : on garde son échéance (ou son état de fichiers).
                same = prev is not None and prev.trigger.model_dump() == t.model_dump()
                if t.type == "after_project":
                    if same and prev.target is not None:
                        w.target, w.seen_ts, w.ends_mtime, w.end = (prev.target, prev.seen_ts,
                                                                    prev.ends_mtime, prev.end)
                    else:
                        from hydra_etl.workflow.subprojects import ProjectRefError, resolve_project
                        try:
                            w.target = resolve_project(t.project, st.root, t.ref)
                        except ProjectRefError as e:
                            w.note = str(e)
                            st.watched[t.name] = w
                            continue
                        w.seen_ts = time.time()     # les fins passées ne déclenchent rien
                    w.next_poll = now
                elif t.type == "source_change":
                    if same:
                        w.value, w.next_poll, w.change = prev.value, prev.next_poll, prev.change
                    else:
                        w.next_poll = now          # première mesure tout de suite : la référence
                elif t.type in FILE_TYPES:
                    if same and prev.watcher is not None:
                        w.watcher, w.pending, w.next_poll = prev.watcher, prev.pending, prev.next_poll
                    else:
                        try:
                            w.watcher = make_watcher(st.root, t)
                        except (OSError, ValueError, NotImplementedError) as e:
                            w.note = f"cannot watch {t.path}: {e}"
                            st.watched[t.name] = w
                            continue
                        w.next_poll = now + timedelta(seconds=_poll_every(t))
                else:
                    w.next_at = prev.next_at if (same and prev.next_at is not None) else next_time(t, now)
            st.watched[t.name] = w
        self._emit(kind="loaded", project=st.name, warnings=list(check.warnings),
                   triggers=[self.describe(st, w) for w in st.watched.values()])

    # ── boucle ─────────────────────────────────────────────────────────────

    def tick(self, now: Optional[datetime] = None) -> List[str]:
        """Une passe : relit les fichiers modifiés, lance les échéances. Rend les noms lancés."""
        now = now or self.clock()
        started = []
        with self._lock:
            for st in list(self.projects.values()):
                if self._mtime(st.root) != st.mtime:
                    self._load(st, now)
                for w in st.watched.values():
                    if w.watcher is not None:
                        self._tick_files(st, w, now, started)
                        continue
                    if w.trigger.type == "source_change" and w.note is None:
                        self._tick_source(st, w, now, started)
                        continue
                    if w.trigger.type == "after_project" and w.target is not None:
                        self._tick_after(st, w, now, started)
                        continue
                    if w.next_at is None or now < w.next_at:
                        continue
                    due = w.next_at
                    w.next_at = next_time(w.trigger, max(now, due))
                    if self._stop.is_set():
                        continue
                    if w.running:
                        msg = "the previous run of this trigger is still running"
                        record(st.root, {"trigger": w.trigger.name, "type": w.trigger.type,
                                         "origin": self.origin, "status": "skipped", "attempt": 1,
                                         "env": w.trigger.env or self.env, "duration": 0,
                                         "error": msg, "detail": None})
                        self._emit(kind="skipped", project=st.name, trigger=w.trigger.name, error=msg)
                        continue
                    self._start(st, w, due)
                    started.append(w.trigger.name)
        return started

    def _tick_files(self, st: ProjectState, w: Watched, now: datetime, started: List[str]) -> None:
        """Scrute le dossier à son rythme ; lance un run pour les fichiers en attente."""
        t = w.trigger
        if w.next_poll is None or now >= w.next_poll:
            w.next_poll = now + timedelta(seconds=_poll_every(t))
            try:
                for ev in w.watcher.poll(now.timestamp()):
                    if ev.path not in w.pending:
                        w.pending.append(ev.path)
            except (OSError, NotImplementedError) as e:
                self._emit(kind="error", project=st.name, error=f"trigger '{t.name}': {e}", kept=[])
        if not w.pending or w.running or self._stop.is_set():
            return
        files, w.pending = list(w.pending), []
        if t.type == "marker" and t.consume is not False:
            for f in files:
                try:
                    w.watcher.source.delete(f)
                    w.watcher.known.pop(f, None)
                except (OSError, ValueError) as e:
                    self._emit(kind="error", project=st.name,
                               error=f"trigger '{t.name}': marker {f} not removed: {e}", kept=[])
        extra = {"trigger.file": files[0], "trigger.files": ",".join(files)}
        self._start(st, w, now, extra=extra, detail="files: " + ", ".join(files))
        started.append(t.name)

    def _tick_source(self, st: ProjectState, w: Watched, now: datetime, started: List[str]) -> None:
        """Mesure la source à son rythme (thread à part) ; lance un run quand la valeur change."""
        t = w.trigger
        if w.measured is not None:
            value, error = w.measured
            w.measured = None
            if error:
                self._emit(kind="error", project=st.name, error=f"trigger '{t.name}': {error}", kept=[])
            elif w.value is None:
                w.value = value
                self._emit(kind="measured", project=st.name, trigger=t.name, value=value)
            elif value != w.value:
                before = w.change[0] if w.change else w.value
                w.change, w.value = (before, value), value
        if w.change and not w.running and not self._stop.is_set():
            before, after = w.change
            w.change = None
            self._start(st, w, now, extra={"trigger.value": after, "trigger.previous": before},
                        detail=f"source {t.source.id}: {before} → {after}")
            started.append(t.name)
        if not w.measuring and (w.next_poll is None or now >= w.next_poll) and not self._stop.is_set():
            w.next_poll = now + timedelta(seconds=_poll_every(t))
            w.measuring = True

            def run() -> None:
                try:
                    res = (self.measure_fn(st.root, t.source, t.env or self.env), None)
                except Exception as e:  # noqa: BLE001
                    res = (None, str(e))
                with self._lock:
                    w.measured, w.measuring = res, False

            threading.Thread(target=run, name=f"measure-{t.name}", daemon=True).start()

    def _tick_after(self, st: ProjectState, w: Watched, now: datetime, started: List[str]) -> None:
        """Relit les fins du projet suivi ; lance un run pour une fin qui correspond à `on`."""
        from hydra_etl.triggers.core import ends_file, read_ends
        t = w.trigger
        if w.next_poll is None or now >= w.next_poll:
            w.next_poll = now + timedelta(seconds=DEFAULT_POLL)
            try:
                fst = ends_file(w.target).stat()
                mtime = (fst.st_mtime, fst.st_size)
            except OSError:
                mtime = None
            if mtime is not None and mtime != w.ends_mtime:
                w.ends_mtime = mtime
                for e in read_ends(w.target, w.seen_ts):
                    w.seen_ts = max(w.seen_ts, float(e.get("ts") or 0))
                    if t.on_effective in ("any", "success" if e.get("status") == "success" else "failure"):
                        w.end = e
        if w.end is None or w.running or self._stop.is_set():
            return
        e, w.end = w.end, None
        from hydra_etl.workflow.subprojects import _project_name
        name = _project_name(w.target)
        self._start(st, w, now, extra={"trigger.project": name, "trigger.status": str(e.get("status"))},
                    detail=f"project {name} ended: {e.get('status')}")
        started.append(t.name)

    def fire_now(self, root: Path, name: str, origin: str,
                 extra: Optional[Dict[str, Any]] = None, detail: Optional[str] = None) -> str:
        """Lance un déclencheur tout de suite (webhook, API, Studio), quel que soit son type.
        Rend « started », ou lève LookupError (inconnu / invalide) ou
        RuntimeError (déjà en cours dans ce moteur)."""
        root = Path(root).resolve()
        with self._lock:
            st = self.projects.get(root) or self.add_project(root)
            if self._mtime(st.root) != st.mtime:
                self._load(st, self.clock())
            w = st.watched.get(name)
            if w is None:
                raise LookupError(f"trigger '{name}' not found in triggers.yaml")
            # Un déclencheur désactivé se lance quand même à la main (comme hdrctl trigger fire) ;
            # le webhook, lui, refuse un déclencheur désactivé avant d'arriver ici.
            if w.note and w.trigger.enabled and not w.note.startswith("type "):
                raise LookupError(f"trigger '{name}': {w.note}")
            if w.running:
                raise RuntimeError(f"trigger '{name}' is already running")
            self._start(st, w, self.clock(), extra=extra, detail=detail or origin, origin=origin)
        return "started"

    def _start(self, st: ProjectState, w: Watched, due: datetime,
               extra: Optional[Dict[str, Any]] = None, detail: Optional[str] = None,
               origin: Optional[str] = None) -> None:
        w.running = True
        t = w.trigger
        origin = origin or self.origin
        detail = detail or f"{t.when()} — due {due.astimezone().strftime('%Y-%m-%d %H:%M:%S')}"
        self._emit(kind="started", project=st.name, trigger=t.name, when=t.when(),
                   env=t.env or self.env, detail=detail if (extra or origin != self.origin) else None,
                   origin=origin)

        def run() -> None:
            try:
                kw: Dict[str, Any] = {"extra_params": extra} if extra else {}
                res = self.fire_fn(st.root, t, origin=origin, env=self.env, detail=detail,
                                   stop=self._stop, **kw)
            except Exception as e:  # noqa: BLE001
                res = FireResult(t.name, "failed", f"{type(e).__name__}: {e}")
                record(st.root, {"trigger": t.name, "type": t.type, "origin": origin,
                                 "status": "failed", "attempt": 1, "env": t.env or self.env,
                                 "duration": 0, "error": res.error, "detail": detail})
            finally:
                with self._lock:
                    w.running = False
            self._emit(kind="finished", project=st.name, trigger=t.name, status=res.status,
                       error=res.error, duration=res.duration, attempts=res.attempts, lines=res.lines)

        th = threading.Thread(target=run, name=f"trigger-{t.name}", daemon=True)
        self._runs.append(th)
        th.start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:  # noqa: BLE001
                log.exception("trigger engine tick failed")
            self._stop.wait(self.tick_seconds)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="hydra-triggers", daemon=True)
        self._thread.start()

    def running(self) -> List[str]:
        with self._lock:
            return [f"{st.name}/{w.trigger.name}" for st in self.projects.values()
                    for w in st.watched.values() if w.running]

    def stop(self, wait: Optional[float] = None) -> bool:
        """Plus aucun lancement ; attend les runs en cours (wait secondes, None = sans limite).
        Rend True si tout est terminé."""
        self._stop.set()
        n = len(self.running())
        if n:
            self._emit(kind="stopping", running=self.running())
        deadline = None if wait is None else time.monotonic() + wait
        for th in list(self._runs):
            left = None if deadline is None else max(0.0, deadline - time.monotonic())
            th.join(left)
        if self._thread is not None:
            self._thread.join(2)
            self._thread = None
        return not self.running()

    # ── état ───────────────────────────────────────────────────────────────

    @staticmethod
    def describe(st: ProjectState, w: Watched) -> Dict[str, Any]:
        return {"project": st.name, "trigger": w.trigger.name, "type": w.trigger.type,
                "when": w.trigger.when(), "next": w.next_at, "running": w.running, "note": w.note,
                "poll": (DEFAULT_POLL if w.trigger.type == "after_project" else _poll_every(w.trigger))
                if (w.watcher is not None or (w.trigger.type in ("source_change", "after_project")
                                              and w.note is None)) else None,
                "pending": list(w.pending), "value": w.value}

    def status(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [self.describe(st, w) for st in self.projects.values() for w in st.watched.values()]
