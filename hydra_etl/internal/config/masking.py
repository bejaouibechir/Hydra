"""
Masquage des secrets dans tout ce que Hydra affiche ou conserve.

Visibilité, au choix de l'utilisateur (comme les variables GitLab) :

- ``plain``  : aucune protection (débogage) ; un avertissement le rappelle ;
- ``masked`` : la valeur est remplacée par ``[MASKED]`` (défaut) ;
- ``hidden`` : la ligne qui contient la valeur est omise, remplacée par un
  repère qui dit combien de lignes ont été retirées (jamais de silence).

Réglage, du plus fort au plus faible :
``--secrets-visibility`` (CLI) > ``HYDRA_SECRETS_VISIBILITY`` >
``visibility:`` de ``.hydra/secrets.yaml`` > ``masked``.

Fonctionnement : chaque valeur de secret lue (``${SECRET:...}``, fichier du
projet, fournisseur) est enregistrée ici. Ensuite :

- tous les logs passent par une fabrique de LogRecord qui réécrit le message
  et la trace d'exception (couvre le logger de chaque step, l'API, le CLI) ;
- ``redact_text`` / ``redact_lines`` / ``redact_result`` nettoient les
  messages d'erreur, la sortie des actions (bash, powershell, python, ssh,
  webhook, email), les résultats de workflow, le rapport d'annulation et les
  runs enregistrés par l'API ;
- le CLI enveloppe stdout / stderr (``install_stream_redaction``).

Seul l'affichage est concerné : les valeurs envoyées aux connecteurs, aux
scripts et aux webhooks restent intactes.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import threading
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import quote, quote_plus

VISIBILITY_ENV = "HYDRA_SECRETS_VISIBILITY"
VISIBILITIES = ("plain", "masked", "hidden")
DEFAULT_VISIBILITY = "masked"
MASK = "[MASKED]"
# Plus court, une valeur n'est pas masquée (elle effacerait des mots
# ordinaires dans les logs) : un avertissement le signale, une fois.
MIN_LENGTH = 4

_RANK = {"plain": 0, "masked": 1, "hidden": 2}
_logger = logging.getLogger(__name__)


class VisibilityError(ValueError):
    pass


def check_visibility(value: Any, source: str = "visibility") -> str:
    v = str(value or "").strip().lower()
    if v not in VISIBILITIES:
        raise VisibilityError(
            f"{source}: invalid secrets visibility '{value}' "
            f"(expected one of: {', '.join(VISIBILITIES)})")
    return v


def resolve_visibility(configured: Optional[str] = None) -> str:
    """HYDRA_SECRETS_VISIBILITY > valeur du projet > masked."""
    env = os.environ.get(VISIBILITY_ENV)
    if env:
        return check_visibility(env, VISIBILITY_ENV)
    if configured:
        return check_visibility(configured)
    return DEFAULT_VISIBILITY


# ── Registre des valeurs ────────────────────────────────────────────────────
_lock = threading.RLock()
_values: Dict[str, str] = {}          # forme affichable -> visibilité
_masked_re: Optional[re.Pattern] = None
_hidden_re: Optional[re.Pattern] = None
_warned: set = set()


def _variants(value: str) -> List[str]:
    """Formes sous lesquelles la valeur peut apparaître dans un log : brute,
    encodée dans une URL (DSN), échappée en JSON ; et chaque ligne d'une
    valeur multiligne (clé PEM)."""
    out = {value, quote(value, safe=""), quote_plus(value), json.dumps(value)[1:-1]}
    if "\n" in value:
        out.update(ln.strip() for ln in value.splitlines())
    return [v for v in out if len(v) >= MIN_LENGTH]


def _warn_once(key: str, message: str) -> None:
    if key in _warned:
        return
    _warned.add(key)
    _logger.warning(message)


def register(value: Any, visibility: Optional[str] = None, name: Optional[str] = None) -> None:
    """Enregistre la valeur d'un secret pour la masquer partout."""
    if value is None:
        return
    mode = check_visibility(visibility) if visibility else resolve_visibility()
    if mode == "plain":
        _warn_once("plain", "secrets visibility is 'plain': secret values are shown "
                            "in logs and messages (debugging only)")
        return
    s = str(value)
    if not s.strip():
        return
    if len(s.strip()) < MIN_LENGTH:
        label = f"'{name}'" if name else "a secret"
        _warn_once(f"short:{name}", f"{label} is shorter than {MIN_LENGTH} characters "
                                    "and cannot be masked in logs")
        return
    global _masked_re, _hidden_re
    with _lock:
        changed = False
        for v in _variants(s):
            if _RANK[mode] > _RANK.get(_values.get(v, "plain"), 0):
                _values[v] = mode
                changed = True
        if changed:
            _masked_re = _compile([v for v, m in _values.items() if m == "masked"])
            _hidden_re = _compile([v for v, m in _values.items() if m == "hidden"])
    _install_log_factory()


def _compile(values: Iterable[str]) -> Optional[re.Pattern]:
    vals = sorted(set(values), key=len, reverse=True)
    return re.compile("|".join(re.escape(v) for v in vals)) if vals else None


def clear() -> None:
    """Oublie toutes les valeurs (tests)."""
    global _masked_re, _hidden_re
    with _lock:
        _values.clear()
        _masked_re = _hidden_re = None
        _warned.clear()


def active() -> bool:
    return _masked_re is not None or _hidden_re is not None


# ── Nettoyage ───────────────────────────────────────────────────────────────
def _hidden_marker(n: int) -> str:
    return f"[{n} line(s) hidden: they contain a secret]"


def redact_text(text: Any) -> Any:
    """Masque les secrets d'une chaîne (les autres types sont rendus tels quels)."""
    if not isinstance(text, str) or not text:
        return text
    m_re, h_re = _masked_re, _hidden_re
    if m_re is None and h_re is None:
        return text
    if h_re is not None and h_re.search(text):
        kept: List[str] = []
        dropped = 0
        for line in text.split("\n"):
            if h_re.search(line):
                dropped += 1
                continue
            if dropped:
                kept.append(_hidden_marker(dropped))
                dropped = 0
            kept.append(line)
        if dropped:
            kept.append(_hidden_marker(dropped))
        text = "\n".join(kept)
    if m_re is not None:
        text = m_re.sub(MASK, text)
    return text


def redact_lines(lines: Optional[List[Any]]) -> List[Any]:
    """Une liste de lignes (logs, sortie d'action) : chaque ligne masquée ; en
    `hidden`, les lignes concernées sont retirées et un repère les compte."""
    if not lines or not active():
        return list(lines or [])
    out: List[Any] = []
    dropped = 0
    h_re = _hidden_re
    for line in lines:
        if isinstance(line, str) and h_re is not None and h_re.search(line):
            dropped += 1
            continue
        if dropped:
            out.append(_hidden_marker(dropped))
            dropped = 0
        out.append(redact_text(line))
    if dropped:
        out.append(_hidden_marker(dropped))
    return out


def redact_data(data: Any) -> Any:
    """dict / list / str, récursivement (copie ; l'original n'est pas touché)."""
    if not active():
        return data
    if isinstance(data, str):
        return redact_text(data)
    if isinstance(data, dict):
        return {k: redact_data(v) for k, v in data.items()}
    if isinstance(data, list):
        if all(isinstance(x, str) for x in data):
            return redact_lines(data)
        return [redact_data(x) for x in data]
    if isinstance(data, tuple):
        return tuple(redact_data(list(data)))
    return data


# Champs texte des résultats (StepResult, WorkflowResult, JobResult). Les
# autres champs (connecteur d'annulation, échantillon de données) ne sont pas
# touchés : ils servent encore après le run.
_TEXT_FIELDS = ("error", "message")
_LINE_FIELDS = ("logs", "output")


def redact_result(obj: Any) -> Any:
    """Nettoie EN PLACE un objet résultat (et ses steps / job_result)."""
    if obj is None or not active():
        return obj
    for f in _TEXT_FIELDS:
        if isinstance(getattr(obj, f, None), str):
            setattr(obj, f, redact_text(getattr(obj, f)))
    for f in _LINE_FIELDS:
        v = getattr(obj, f, None)
        if isinstance(v, list):
            setattr(obj, f, redact_lines(v))
    rb = getattr(obj, "rollback", None)
    if isinstance(rb, dict):
        obj.rollback = redact_data(rb)
    for s in getattr(obj, "steps", None) or []:
        if not isinstance(s, (str, dict)):
            redact_result(s)
    jr = getattr(obj, "job_result", None)
    if jr is not None:
        redact_result(jr)
    return obj


def redact_model(model: Any) -> Any:
    """Modèle Pydantic nettoyé EN PLACE (champs texte, listes, dicts, sous-modèles)."""
    if model is None or not active():
        return model
    fields = getattr(type(model), "model_fields", None)
    if not fields:
        return model
    for name in fields:
        v = getattr(model, name, None)
        if hasattr(type(v), "model_fields"):
            redact_model(v)
            continue
        if isinstance(v, list) and v and all(hasattr(type(x), "model_fields") for x in v):
            for x in v:
                redact_model(x)
            continue
        nv = redact_data(v)
        if nv is not v and nv != v:
            object.__setattr__(model, name, nv)
    return model


# ── Logs : fabrique de LogRecord ────────────────────────────────────────────
_factory_installed = False


def _install_log_factory() -> None:
    global _factory_installed
    if _factory_installed:
        return
    with _lock:
        if _factory_installed:
            return
        previous = logging.getLogRecordFactory()

        def factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
            record = previous(*args, **kwargs)
            if not active():
                return record
            try:
                msg = record.getMessage()
            except Exception:  # noqa: BLE001 — message mal formé : laissé au handler
                return record
            clean = redact_text(msg)
            if clean != msg:
                record.msg, record.args = clean, None
            if record.exc_info and record.exc_info[0] is not None:
                import traceback
                text = "".join(traceback.format_exception(*record.exc_info)).rstrip("\n")
                record.exc_text = redact_text(text)
            return record

        logging.setLogRecordFactory(factory)
        _install_excepthooks()
        _factory_installed = True


def _install_excepthooks() -> None:
    """Exception non rattrapée : la trace affichée est masquée aussi."""
    import traceback
    prev_sys = sys.excepthook

    def sys_hook(tp, val, tb):  # type: ignore[no-untyped-def]
        if not active():
            return prev_sys(tp, val, tb)
        sys.stderr.write(redact_text("".join(traceback.format_exception(tp, val, tb))))

    sys.excepthook = sys_hook
    prev_thread = threading.excepthook

    def thread_hook(args):  # type: ignore[no-untyped-def]
        if not active():
            return prev_thread(args)
        sys.stderr.write(redact_text("".join(traceback.format_exception(
            args.exc_type, args.exc_value, args.exc_traceback))))

    threading.excepthook = thread_hook


# ── CLI : stdout / stderr ───────────────────────────────────────────────────
class _RedactingStream:
    """Enveloppe d'un flux texte : chaque write() est masqué. Le reste
    (isatty, encoding, buffer, flush...) est délégué au flux d'origine."""

    _hydra_redacting = True

    def __init__(self, stream: Any) -> None:
        self._stream = stream

    def write(self, s: Any) -> Any:
        if isinstance(s, str) and active():
            s = redact_text(s)
        return self._stream.write(s)

    def writelines(self, lines: Iterable[Any]) -> None:
        for ln in lines:
            self.write(ln)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._stream, name)


def install_stream_redaction() -> None:
    """Enveloppe sys.stdout / sys.stderr (idempotent)."""
    for attr in ("stdout", "stderr"):
        s = getattr(sys, attr)
        if s is not None and not getattr(s, "_hydra_redacting", False):
            setattr(sys, attr, _RedactingStream(s))
    _install_log_factory()
