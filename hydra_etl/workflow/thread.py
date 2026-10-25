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

Boucles (facultatives) : rejouer une portion du thread N fois.

    loops:
      - from: workflow5      # dernier workflow de la portion répétée
        to: workflow1        # premier workflow de la portion
        times: 3             # nombre total de passages (1 = pas de reprise)
        delay: 5m            # pause avant chaque reprise (optionnel)

- `to` doit venir avant `from` dans le thread (ou être le même workflow).
- Dans une étape `parallel`, les workflows n'ont pas d'ordre : une boucle qui y
  commence reprend toute l'étape ; une boucle qui y finit attend toute l'étape.
- Plusieurs boucles sont possibles si leurs portions ne se chevauchent pas.
- Un échec arrête le projet, boucles comprises.

Fallback (facultatif) : un workflow de secours, déclaré sur le workflow visé.

      - name: load_crm
        fallback:
          use: [load_crm_backup]                  # remplaçants, dans l'ordre
          when: "not source_available('crm_db')"  # vérifié juste avant le lancement
          on_failure: true                        # aussi après un échec (rien publié)
          on_probe_error: keep                    # sonde en erreur : keep | replace

- Les remplaçants sont des fichiers `workflows/<nom>.yaml` qui ne figurent pas
  dans le thread ; un remplaçant n'a pas de fallback (profondeur 1).
- `when` : langage restreint (`workflow/conditions.py`), jamais `eval`.
- Un remplaçant prend la place du workflow à la même position (étape, boucle).
- Un workflow inactif n'évalue pas son fallback.
"""
from __future__ import annotations

import json
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


class ThreadFallback(BaseModel):
    """Workflow(s) de secours d'un workflow du thread."""
    model_config = ConfigDict(extra="forbid")
    use: List[str] = Field(min_length=1)          # remplaçants, essayés dans l'ordre
    when: Optional[str] = None                    # condition évaluée avant le lancement
    on_failure: bool = False                      # bascule aussi après un échec
    on_probe_error: Literal["keep", "replace"] = "keep"

    @field_validator("use", mode="before")
    @classmethod
    def _one_or_many(cls, v: Any) -> Any:
        return [v] if isinstance(v, str) else v

    @field_validator("use")
    @classmethod
    def _check_use(cls, v: List[str]) -> List[str]:
        names = [ThreadWorkflow._check_name(n) for n in v]
        dup = sorted({n for n in names if names.count(n) > 1})
        if dup:
            raise ValueError(f"fallback 'use' lists {', '.join(dup)} more than once")
        return names

    @field_validator("when")
    @classmethod
    def _check_when(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not str(v).strip():
            return None
        from hydra_etl.workflow.conditions import ConditionError, parse_condition
        try:
            parse_condition(str(v))
        except ConditionError as e:
            raise ValueError(str(e)) from None
        return str(v).strip()

    @model_validator(mode="after")
    def _has_trigger(self) -> "ThreadFallback":
        if self.when is None and not self.on_failure:
            raise ValueError("fallback needs 'when' (checked before the start) "
                             "and/or 'on_failure: true'")
        return self


class ThreadWorkflow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    active: bool = True
    fallback: Optional[ThreadFallback] = None

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


MAX_LOOP_TIMES = 1000


class ThreadLoop(BaseModel):
    """Boucle : rejouer la portion du thread qui va de `to` à `from`."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    from_: str = Field(alias="from")
    to: str
    times: int = Field(ge=1, le=MAX_LOOP_TIMES)
    delay: Optional[Union[int, float, str]] = None

    @field_validator("from_", "to")
    @classmethod
    def _check_names(cls, v: str) -> str:
        return ThreadWorkflow._check_name(v)

    @field_validator("delay")
    @classmethod
    def _check_delay(cls, v: Any) -> Any:
        parse_delay(v)
        return v

    @property
    def delay_seconds(self) -> float:
        return parse_delay(self.delay)


class ThreadUnit(BaseModel):
    """Unité d'exécution : un workflow d'une étape séquentielle, ou une étape
    parallèle entière. Les boucles et les délais se placent entre unités."""
    stage: int                       # index de l'étape (0-based)
    names: List[str]
    parallel: bool
    last_in_stage: bool


class ThreadDef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str = "1.0"
    thread: List[ThreadStage] = Field(default_factory=list)
    loops: List[ThreadLoop] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_names(self) -> "ThreadDef":
        seen: set = set()
        for stage in self.thread:
            for wf in stage.workflows:
                if wf.name in seen:
                    raise ValueError(f"workflow '{wf.name}' appears more than once in the thread")
                seen.add(wf.name)
        return self

    @model_validator(mode="after")
    def _check_fallbacks(self) -> "ThreadDef":
        in_thread = set(self.workflow_names())
        for stage in self.thread:
            for wf in stage.workflows:
                if not wf.fallback:
                    continue
                for alt in wf.fallback.use:
                    if alt == wf.name:
                        raise ValueError(f"workflow '{wf.name}': a fallback cannot be the workflow itself")
                    if alt in in_thread:
                        raise ValueError(f"workflow '{wf.name}': fallback '{alt}' is already in the "
                                         f"thread (it would run twice); use a workflow outside the thread")
        return self

    def fallback_names(self) -> List[str]:
        """Remplaçants cités par les fallbacks (sans doublon, dans l'ordre)."""
        out: List[str] = []
        for stage in self.thread:
            for wf in stage.workflows:
                for alt in (wf.fallback.use if wf.fallback else []):
                    if alt not in out:
                        out.append(alt)
        return out

    @model_validator(mode="after")
    def _check_loops(self) -> "ThreadDef":
        spans = []
        for lp in self.loops:
            for n in (lp.from_, lp.to):
                if n not in self.workflow_names():
                    raise ValueError(f"loop {lp.from_} -> {lp.to}: workflow '{n}' is not in the thread")
            a, b = self.unit_of(lp.to), self.unit_of(lp.from_)
            if a > b:
                raise ValueError(f"loop {lp.from_} -> {lp.to}: '{lp.to}' must come before "
                                 f"'{lp.from_}' in the thread (a loop goes back)")
            for (a2, b2, other) in spans:
                if not (b < a2 or b2 < a):
                    raise ValueError(f"loops {other} and {lp.from_} -> {lp.to} overlap; "
                                     f"loops must cover separate parts of the thread")
            spans.append((a, b, f"{lp.from_} -> {lp.to}"))
        return self

    def workflow_names(self) -> List[str]:
        return [wf.name for stage in self.thread for wf in stage.workflows]

    def units(self) -> List[ThreadUnit]:
        out: List[ThreadUnit] = []
        for si, st in enumerate(self.thread):
            if st.mode == "parallel":
                out.append(ThreadUnit(stage=si, names=[w.name for w in st.workflows],
                                      parallel=True, last_in_stage=True))
            else:
                n = len(st.workflows)
                out.extend(ThreadUnit(stage=si, names=[w.name], parallel=False,
                                      last_in_stage=(i == n - 1))
                           for i, w in enumerate(st.workflows))
        return out

    def unit_of(self, name: str) -> int:
        for i, u in enumerate(self.units()):
            if name in u.names:
                return i
        raise KeyError(name)


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
        "# Optional loops, to replay a part of the thread N times:",
        "#   loops:",
        "#     - from: workflow1   # last workflow of the part",
        "#       to: workflow1     # first workflow of the part",
        "#       times: 3          # total passes",
        "#       delay: 5m         # pause before each repeat (optional)",
        "# Optional fallback on a workflow (a backup workflow, outside the thread):",
        "#       - name: workflow1",
        "#         fallback:",
        "#           use: [workflow1_backup]                   # tried in order",
        "#           when: \"not source_available('my_db')\"   # checked just before the start",
        "#           on_failure: true                          # also after a failure",
        'version: "1.0"',
        "thread:",
        "  - mode: sequential",
        "    workflows:",
    ]
    for n in workflow_names:
        lines += [f"      - name: {n}", "        active: true"]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Écriture et modification du thread (hdrctl workflow add/remove, Studio)
# ---------------------------------------------------------------------------

_HEADER = default_thread_yaml([]).split('version: "1.0"')[0]


def render_thread(thread: ThreadDef) -> str:
    """ThreadDef → texte de thread.yaml, avec l'en-tête commenté standard.
    Les commentaires ajoutés à la main dans le fichier ne sont pas conservés."""
    lines = [_HEADER.rstrip("\n"), f'version: "{thread.version}"']
    if not thread.thread:
        lines.append("thread: []")
        return "\n".join(lines) + "\n"
    lines.append("thread:")
    for stage in thread.thread:
        lines.append(f"  - mode: {stage.mode}")
        if stage.delay_after not in (None, "", 0):
            lines.append(f"    delay_after: {stage.delay_after}")
        lines.append("    workflows:")
        for wf in stage.workflows:
            lines.append(f"      - name: {wf.name}")
            lines.append(f"        active: {'true' if wf.active else 'false'}")
            if wf.fallback:
                fb = wf.fallback
                lines.append("        fallback:")
                lines.append(f"          use: [{', '.join(fb.use)}]")
                if fb.when:
                    lines.append(f"          when: {json.dumps(fb.when, ensure_ascii=False)}")
                if fb.on_failure:
                    lines.append("          on_failure: true")
                if fb.on_probe_error != "keep":
                    lines.append(f"          on_probe_error: {fb.on_probe_error}")
    if thread.loops:
        lines.append("loops:")
        for lp in thread.loops:
            lines += [f"  - from: {lp.from_}", f"    to: {lp.to}", f"    times: {lp.times}"]
            if lp.delay not in (None, "", 0):
                lines.append(f"    delay: {lp.delay}")
    return "\n".join(lines) + "\n"


def add_to_thread(thread: ThreadDef, name: str) -> ThreadDef:
    """Ajoute `name` en fin de thread : dans la dernière étape si elle est
    séquentielle, sinon dans une nouvelle étape séquentielle."""
    if name in thread.workflow_names():
        raise ValueError(f"workflow '{name}' is already in the thread")
    stages = [s.model_copy(deep=True) for s in thread.thread]
    new = ThreadWorkflow(name=name)
    if stages and stages[-1].mode == "sequential":
        stages[-1].workflows.append(new)
    else:
        stages.append(ThreadStage(mode="sequential", workflows=[new]))
    return ThreadDef(version=thread.version, thread=stages, loops=list(thread.loops))


def remove_from_thread(thread: ThreadDef, name: str) -> "tuple[ThreadDef, bool]":
    """Retire `name` du thread ; une étape devenue vide disparaît.
    Retourne (thread, trouvé)."""
    found = False
    stages: List[ThreadStage] = []
    for s in thread.thread:
        kept = [w for w in s.workflows if w.name != name]
        found = found or len(kept) != len(s.workflows)
        if kept:
            stages.append(s.model_copy(update={"workflows": kept}, deep=True))
    # Une boucle qui cite ce workflow n'a plus de sens : elle part avec lui.
    loops = [lp for lp in thread.loops if name not in (lp.from_, lp.to)]
    # Il n'est plus remplaçant de personne ; un fallback sans remplaçant disparaît.
    stages = [_drop_fallback_ref(s, name) for s in stages]
    return ThreadDef(version=thread.version, thread=stages, loops=loops), found


def _drop_fallback_ref(stage: ThreadStage, name: str) -> ThreadStage:
    wfs = []
    for w in stage.workflows:
        if w.fallback and name in w.fallback.use:
            rest = [n for n in w.fallback.use if n != name]
            fb = w.fallback.model_copy(update={"use": rest}) if rest else None
            w = w.model_copy(update={"fallback": fb})
        wfs.append(w)
    return stage.model_copy(update={"workflows": wfs})
