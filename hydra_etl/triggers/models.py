"""triggers.yaml : modèle, lecture et validation.

    version: "1.0"
    triggers:
      - name: nightly
        type: cron              # cron | interval | file | marker | source_change | webhook | after_project
        cron: "0 2 * * *"
        env: prod               # défaut : l'environnement de hdrctl watch / serve (--env)
        workflows: [ingest]     # défaut : le thread.yaml du projet
        params: {run_date: "2026-11-02"}
        overlap: skip           # projet déjà en cours : skip (défaut) | wait | fail
        timeout: 1h
        retry: {max: 2, delay: 5m}
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

TRIGGERS_FILE = "triggers.yaml"
TRIGGER_TYPES = ("cron", "interval", "file", "marker", "source_change", "webhook", "after_project")
FILE_EVENTS = ("added", "modified")
SOURCE_CHECKS = ("count", "max", "checksum")

_NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-]*$")
_ENV_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_\-]*$")
_SECRET_REF_RE = re.compile(r"^\$\{SECRET:[A-Za-z0-9_.\-]+\}$")

# Clés propres à chaque type (les autres clés de type sont refusées)
TYPE_KEYS: Dict[str, tuple] = {
    "cron": ("cron", "timezone"),
    "interval": ("every",),
    "file": ("path", "events", "debounce", "every"),
    "marker": ("path", "consume", "every"),
    "source_change": ("source", "every"),
    "webhook": ("token",),
    "after_project": ("project", "ref", "on"),
}
REQUIRED_KEYS: Dict[str, tuple] = {
    "cron": ("cron",), "interval": ("every",), "file": ("path",), "marker": ("path",),
    "source_change": ("source",), "webhook": ("token",), "after_project": ("project",),
}
ALL_TYPE_KEYS = sorted({k for ks in TYPE_KEYS.values() for k in ks})


class TriggerFileError(ValueError):
    """triggers.yaml illisible ou invalide (liste de messages dans `errors`)."""

    def __init__(self, errors: List[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def _delay(value: Any, what: str, positive: bool = True) -> float:
    from hydra_etl.workflow.thread import parse_delay
    try:
        secs = parse_delay(value)
    except ValueError as e:
        raise ValueError(f"{what}: {e}") from None
    if positive and secs <= 0:
        raise ValueError(f"{what} must be more than 0")
    return secs


def check_cron(expr: str, timezone: Optional[str] = None) -> None:
    """Expression cron à 5 champs (vérifiée par APScheduler s'il est installé)."""
    if len(str(expr).split()) != 5:
        raise ValueError(f"cron '{expr}': 5 fields expected (minute hour day month weekday)")
    try:
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:  # extra [server] absent : contrôle de forme seulement
        return
    try:
        CronTrigger.from_crontab(str(expr), timezone=timezone)
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"cron '{expr}': {e}") from None


class RetryOnFailure(BaseModel):
    """E3 : relance du projet après un échec."""
    model_config = ConfigDict(extra="forbid")
    max: int = 1
    delay: Union[int, float, str] = "1m"

    @model_validator(mode="after")
    def _check(self) -> "RetryOnFailure":
        if not 1 <= self.max <= 10:
            raise ValueError("retry.max must be between 1 and 10")
        _delay(self.delay, "retry.delay", positive=False)
        return self


class SourceRef(BaseModel):
    """B4 : la source surveillée (déclarée dans un job du projet)."""
    model_config = ConfigDict(extra="forbid")
    job: str                         # dossier du job, relatif à la racine du projet
    id: str                          # id de la source dans son sources.yaml
    check: Literal["count", "max", "checksum"] = "count"
    column: Optional[str] = None     # check: max

    @model_validator(mode="after")
    def _check(self) -> "SourceRef":
        if self.check == "max" and not self.column:
            raise ValueError("source.check: max requires source.column")
        if self.check != "max" and self.column:
            raise ValueError("source.column applies to check: max")
        return self


class ProjectTrigger(BaseModel):
    """Un déclencheur du projet."""
    model_config = ConfigDict(extra="forbid")

    name: str
    type: Literal["cron", "interval", "file", "marker", "source_change", "webhook", "after_project"]
    description: Optional[str] = None
    enabled: bool = True
    # ce qui est lancé
    env: Optional[str] = None
    workflows: Optional[List[str]] = None
    params: Optional[Dict[str, Any]] = None
    overlap: Literal["wait", "skip", "fail"] = "skip"
    timeout: Optional[Union[int, float, str]] = None
    retry: Optional[RetryOnFailure] = None
    # propres au type
    cron: Optional[str] = None
    timezone: Optional[str] = None
    every: Optional[Union[int, float, str]] = None
    path: Optional[str] = None
    events: Optional[List[Literal["added", "modified"]]] = None
    debounce: Optional[Union[int, float, str]] = None
    consume: Optional[bool] = None
    source: Optional[SourceRef] = None
    token: Optional[str] = None
    project: Optional[str] = None
    ref: Optional[Literal["path", "name"]] = None
    on: Optional[Literal["success", "failure", "any"]] = None

    @model_validator(mode="after")
    def _validate(self) -> "ProjectTrigger":
        n = self.name
        if not _NAME_RE.match(n):
            raise ValueError(f"trigger name '{n}': letters, digits, '.', '_' or '-'")
        t = self.type
        for k in REQUIRED_KEYS[t]:
            if getattr(self, k) in (None, ""):
                raise ValueError(f"trigger '{n}': type {t} requires '{k}'")
        extra = [k for k in ALL_TYPE_KEYS if k not in TYPE_KEYS[t] and getattr(self, k) is not None]
        if extra:
            raise ValueError(f"trigger '{n}': {', '.join(extra)} "
                             f"{'does' if len(extra) == 1 else 'do'} not apply to type {t}")
        if self.env is not None and not _ENV_RE.match(self.env):
            raise ValueError(f"trigger '{n}': env '{self.env}' — letters, digits, '_' or '-'")
        if self.workflows is not None:
            if not self.workflows:
                raise ValueError(f"trigger '{n}': workflows is empty — remove it or list names")
            for w in self.workflows:
                if not isinstance(w, str) or not _NAME_RE.match(w):
                    raise ValueError(f"trigger '{n}': workflows: invalid name '{w}'")
        for k, v in (self.params or {}).items():
            if not _NAME_RE.match(str(k)):
                raise ValueError(f"trigger '{n}': params: invalid parameter name '{k}'")
            if isinstance(v, str) and "${SECRET:" in v:
                raise ValueError(f"trigger '{n}': params: '{k}' holds a secret; the project reads "
                                 f"its own secrets (.hydra/secrets)")
        if self.timeout is not None:
            _delay(self.timeout, f"trigger '{n}': timeout")
        if self.every is not None:
            _delay(self.every, f"trigger '{n}': every")
        if self.debounce is not None:
            _delay(self.debounce, f"trigger '{n}': debounce", positive=False)
        if t == "cron":
            try:
                check_cron(self.cron, self.timezone)
            except ValueError as e:
                raise ValueError(f"trigger '{n}': {e}") from None
        if self.path is not None:
            p = str(self.path).replace("\\", "/")
            if p.startswith("/") or re.match(r"^[A-Za-z]:", p) or ".." in p.split("/"):
                raise ValueError(f"trigger '{n}': path '{self.path}' must stay inside the project "
                                 f"(relative, no '..')")
        if self.events is not None and not self.events:
            raise ValueError(f"trigger '{n}': events is empty — added, modified")
        if t == "webhook" and not _SECRET_REF_RE.match(str(self.token).strip()):
            raise ValueError(f"trigger '{n}': token must be a secret reference, e.g. "
                             f"${{SECRET:trigger.{n}.token}} — never the value itself")
        return self

    # -- valeurs effectives -------------------------------------------------

    @property
    def events_effective(self) -> List[str]:
        return list(self.events or ["added"])

    @property
    def on_effective(self) -> str:
        return self.on or "success"

    def when(self) -> str:
        """Résumé lisible de l'événement (hdrctl trigger list, Studio)."""
        t = self.type
        if t == "cron":
            return f"cron {self.cron}" + (f" ({self.timezone})" if self.timezone else "")
        if t == "interval":
            return f"every {self.every}"
        if t == "file":
            return f"{' or '.join(self.events_effective)}: {self.path}"
        if t == "marker":
            return f"marker file {self.path}" + ("" if self.consume is False else " (removed)")
        if t == "source_change":
            s = self.source
            what = f"max({s.column})" if s.check == "max" else s.check
            return f"source {s.id} of {s.job} changes ({what})"
        if t == "webhook":
            return "HTTP call with token"
        return f"after project {self.project} ({self.on_effective})"


class TriggerFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Optional[str] = "1.0"
    triggers: List[ProjectTrigger] = []

    @model_validator(mode="after")
    def _unique(self) -> "TriggerFile":
        seen = set()
        for t in self.triggers:
            if t.name in seen:
                raise ValueError(f"trigger name '{t.name}' is used twice")
            seen.add(t.name)
        return self

    def get(self, name: str) -> Optional[ProjectTrigger]:
        return next((t for t in self.triggers if t.name == name), None)


def triggers_file(root: Path) -> Path:
    return Path(root) / TRIGGERS_FILE


def _messages(err: ValidationError) -> List[str]:
    out = []
    for e in err.errors():
        loc = [str(x) for x in e.get("loc", ())]
        msg = str(e.get("msg", "")).removeprefix("Value error, ")
        where = ""
        if len(loc) >= 2 and loc[0] == "triggers" and loc[1].isdigit():
            where = f"triggers[{loc[1]}]" + ("." + ".".join(loc[2:]) if len(loc) > 2 else "")
        elif loc:
            where = ".".join(loc)
        out.append(f"{where}: {msg}" if where and not msg.startswith("trigger") else msg)
    return out


def load_triggers(root: Path) -> TriggerFile:
    """Lit triggers.yaml (absent = aucun déclencheur). Lève TriggerFileError."""
    path = triggers_file(root)
    if not path.exists():
        return TriggerFile()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8-sig")) or {}
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as e:
        raise TriggerFileError([f"{TRIGGERS_FILE}: cannot be read: {e}"]) from None
    if not isinstance(data, dict):
        raise TriggerFileError([f"{TRIGGERS_FILE}: a mapping with 'triggers:' is expected"])
    # YAML 1.1 lit la clé `on:` comme le booléen True : on la remet en clé texte.
    for item in data.get("triggers") or []:
        if isinstance(item, dict) and True in item and "on" not in item:
            item["on"] = item.pop(True)
    try:
        return TriggerFile(**data)
    except ValidationError as e:
        raise TriggerFileError(_messages(e)) from None
