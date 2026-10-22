"""
workflow/thread.py — Le « thread » d'un projet : `workflows/thread.yaml`.

Le thread dit dans quel ordre `hdrctl run <projet>` lance les workflows du
projet. Il est fait d'étapes (stages) exécutées l'une après l'autre :

    version: "1.0"
    thread:
      - mode: sequential        # sequential | parallel
        delay_after: 30s        # pause après l'étape (optionnel)
        workflows:
          - name: workflow1     # = workflows/workflow1.yaml
            active: true        # false : ignoré au run (débogage)

- `mode: sequential` : les workflows de l'étape tournent l'un après l'autre ;
  `mode: parallel` : ils tournent en même temps.
- `delay_after` : secondes (nombre) ou durée `30s`, `5m`, `1h`.
- `name` désigne le fichier `workflows/<name>.yaml`.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

THREAD_FILE = "thread.yaml"

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$")
_DELAY_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(ms|s|m|h)?\s*$", re.IGNORECASE)
_DELAY_UNITS = {"ms": 0.001, "s": 1, "m": 60, "h": 3600}


def parse_delay(value: Union[None, int, float, str]) -> float:
    """`30` / `"30s"` / `"5m"` / `"1h"` / `"500ms"` → secondes. None → 0."""
    if value is None:
        return 0.0
    if isinstance(value, bool):
        raise ValueError(f"invalid delay {value!r}")
    if isinstance(value, (int, float)):
        if value < 0:
            raise ValueError(f"delay must be >= 0, got {value}")
        return float(value)
    m = _DELAY_RE.match(str(value))
    if not m:
        raise ValueError(f"invalid delay {value!r} (use a number of seconds or 30s, 5m, 1h)")
    return float(m.group(1)) * _DELAY_UNITS[(m.group(2) or "s").lower()]


class ThreadWorkflow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    active: bool = True

    @field_validator("name")
    @classmethod
    def _check_name(cls, v: str) -> str:
        v = (v or "").strip()
        if v.endswith((".yaml", ".yml")):
            v = v.rsplit(".", 1)[0]
        if not _NAME_RE.match(v):
            raise ValueError(f"invalid workflow name {v!r}")
        return v


class ThreadStage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["sequential", "parallel"] = "sequential"
    delay_after: Optional[Union[int, float, str]] = None
    workflows: List[ThreadWorkflow] = Field(min_length=1)

    @field_validator("delay_after")
    @classmethod
    def _check_delay(cls, v: Any) -> Any:
        parse_delay(v)
        return v

    @property
    def delay_seconds(self) -> float:
        return parse_delay(self.delay_after)


class ThreadDef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str = "1.0"
    thread: List[ThreadStage] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_names(self) -> "ThreadDef":
        seen: set = set()
        for stage in self.thread:
            for wf in stage.workflows:
                if wf.name in seen:
                    raise ValueError(f"workflow '{wf.name}' appears more than once in the thread")
                seen.add(wf.name)
        return self

    def workflow_names(self) -> List[str]:
        return [wf.name for stage in self.thread for wf in stage.workflows]


def _format_errors(e: ValidationError) -> str:
    parts = []
    for err in e.errors():
        loc = ".".join(str(x) for x in err.get("loc", ()))
        msg = err.get("msg", "").removeprefix("Value error, ")
        parts.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(parts)


def parse_thread(data: Any) -> ThreadDef:
    """dict (YAML chargé) → ThreadDef. Lève ValueError avec un message lisible."""
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError("thread.yaml must be a mapping with a 'thread' list")
    try:
        return ThreadDef.model_validate(data)
    except ValidationError as e:
        raise ValueError(_format_errors(e)) from None


def load_thread(path: Path) -> ThreadDef:
    import yaml
    path = Path(path)
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except OSError as e:
        raise ValueError(f"cannot read {path}: {e}") from None
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        raise ValueError(f"invalid YAML in {path.name}: {e}") from None
    return parse_thread(data)


def missing_workflow_files(thread: ThreadDef, workflows_dir: Path) -> List[str]:
    """Noms du thread sans fichier `workflows/<name>.yaml` (ou .yml)."""
    workflows_dir = Path(workflows_dir)
    return [n for n in thread.workflow_names()
            if not (workflows_dir / f"{n}.yaml").is_file()
            and not (workflows_dir / f"{n}.yml").is_file()]


def default_thread_yaml(workflow_names: List[str]) -> str:
    """Contenu commenté de thread.yaml pour un nouveau projet."""
    lines = [
        "# Execution order of this project's workflows (read by `hdrctl run`).",
        "# Stages run one after the other.",
        "#   mode        : sequential (one workflow after the other) | parallel (all at once)",
        "#   delay_after : pause after the stage, in seconds or 30s / 5m / 1h (optional)",
        "#   active      : false skips the workflow without removing it (debugging)",
        "# Each name refers to workflows/<name>.yaml.",
        'version: "1.0"',
        "thread:",
        "  - mode: sequential",
        "    workflows:",
    ]
    for n in workflow_names:
        lines += [f"      - name: {n}", "        active: true"]
    return "\n".join(lines) + "\n"
