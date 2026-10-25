"""
workflow/conditions.py — Langage des conditions de `thread.yaml` (`fallback.when`).

Un petit langage, analysé par Hydra — jamais `eval` de code Python :

    not source_available('crm_db')
    file_size('data/in.csv') < 1MB or file_age('data/in.csv') > 24h
    previous.status == 'failed' and previous.rows < 100

- Opérateurs : `and`, `or`, `not`, parenthèses, comparaisons
  (`==`, `!=`, `<`, `<=`, `>`, `>=`).
- Valeurs : chaînes ('...' ou "..."), nombres, `true` / `false`, durées
  (`500ms`, `30s`, `5m`, `24h`, `7d` → secondes) et tailles (`10KB`, `5MB`,
  `1GB` → octets).
- Fonctions et valeurs : liste fermée (`FUNCTIONS`, `ATTRIBUTES`). Les noms
  réservés à `adapt` (estimation, ressources) sont refusés pour l'instant.

Ce module ne fait que l'ANALYSE (étape 1) : `parse_condition()` vérifie la
syntaxe et renvoie un arbre ; l'évaluation par des sondes vient à l'étape 2.
"""
from __future__ import annotations

import ast
import re
from typing import Dict, List, Tuple

# fonction → nombre d'arguments (tous des chaînes) ; type renvoyé, pour la doc
FUNCTIONS: Dict[str, Tuple[int, str]] = {
    "source_available":      (1, "bool"),     # test de connexion d'une source du projet
    "destination_available": (1, "bool"),     # test de connexion d'une destination
    "file_exists":           (1, "bool"),
    "file_size":             (1, "bytes"),
    "file_age":              (1, "seconds"),  # depuis la dernière modification
    "url_ok":                (1, "bool"),     # réponse HTTP 2xx/3xx
    "secret_defined":        (1, "bool"),     # secret présent (.hydra/secrets ou environnement)
    "db.load":               (1, "number"),   # sessions actives sur une base du projet
}

# valeurs `objet.attribut` sans appel
ATTRIBUTES = {
    "previous.status",   # success | failed | skipped | inactive | none
    "previous.rows",     # lignes écrites par le workflow précédent
}

# aide affichée par Studio : (type d'argument, description) — mêmes clés que FUNCTIONS
FUNCTION_HELP: Dict[str, Tuple[str, str]] = {
    "source_available":      ("source", "the source answers (connection test, or the file is there)"),
    "destination_available": ("destination", "the destination answers (or its folder is writable)"),
    "file_exists":           ("path", "the file exists (path relative to the project)"),
    "file_size":             ("path", "size of the file, e.g. file_size('in.csv') < 1MB"),
    "file_age":              ("path", "time since the last change, e.g. file_age('in.csv') > 24h"),
    "url_ok":                ("url", "the URL answers with HTTP 2xx/3xx"),
    "secret_defined":        ("secret", "the secret is set (.hydra/secrets or environment)"),
    "db.load":               ("database", "active queries on a database source or destination"),
}

ATTRIBUTE_HELP: Dict[str, str] = {
    "previous.status": "status of the previous workflow: 'success', 'failed', 'skipped', 'inactive', 'none'",
    "previous.rows":   "rows written by the previous workflow",
}

# réservés au mécanisme `adapt` (plus tard) : refusés avec un message clair
RESERVED = ("estimate", "resources", "volume", "deadline")

_UNITS = {
    "ms": 0.001, "s": 1, "m": 60, "h": 3600, "d": 86400,
    "kb": 1024, "mb": 1024 ** 2, "gb": 1024 ** 3,
}
_LITERAL_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)(ms|s|m|h|d|kb|mb|gb)\b", re.IGNORECASE)
_STRING_RE = re.compile(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"")
_COMPARE_OPS = (ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE)


class ConditionError(ValueError):
    """Condition mal écrite (message en anglais, prêt à afficher)."""


def _expand_units(text: str) -> str:
    """`24h` → `86400`, `1MB` → `1048576`, hors chaînes de caractères."""
    out, pos = [], 0
    for m in _STRING_RE.finditer(text):
        out.append(_LITERAL_RE.sub(_unit_value, text[pos:m.start()]))
        out.append(m.group(0))
        pos = m.end()
    out.append(_LITERAL_RE.sub(_unit_value, text[pos:]))
    return "".join(out)


def _unit_value(m: "re.Match[str]") -> str:
    v = float(m.group(1)) * _UNITS[m.group(2).lower()]
    return repr(int(v)) if v == int(v) else repr(v)


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_dotted(node.value)}.{node.attr}"
    raise ConditionError("only names like source_available or previous.status are allowed")


def _check(node: ast.AST, used: List[str]) -> None:
    if isinstance(node, ast.BoolOp):
        for v in node.values:
            _check(v, used)
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        _check(node.operand, used)
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) \
            and isinstance(node.operand, ast.Constant):
        return
    elif isinstance(node, ast.Compare):
        if not all(isinstance(op, _COMPARE_OPS) for op in node.ops):
            raise ConditionError("only ==, !=, <, <=, >, >= comparisons are allowed")
        _check(node.left, used)
        for c in node.comparators:
            _check(c, used)
    elif isinstance(node, ast.Call):
        name = _dotted(node.func)
        _reserved(name)
        if name not in FUNCTIONS:
            raise ConditionError(f"unknown function {name}() — use one of: "
                                 + ", ".join(f"{f}()" for f in FUNCTIONS))
        if node.keywords:
            raise ConditionError(f"{name}() takes positional arguments only")
        want = FUNCTIONS[name][0]
        if len(node.args) != want:
            raise ConditionError(f"{name}() takes {want} argument(s), got {len(node.args)}")
        for a in node.args:
            if not (isinstance(a, ast.Constant) and isinstance(a.value, str) and a.value.strip()):
                raise ConditionError(f"{name}() expects a quoted name or path, e.g. {name}('crm_db')")
        used.append(name)
    elif isinstance(node, (ast.Attribute, ast.Name)):
        name = _dotted(node)
        if name in ("true", "false", "True", "False"):
            return
        _reserved(name)
        if name not in ATTRIBUTES:
            if name in FUNCTIONS:
                raise ConditionError(f"{name} is a function: write {name}('...')")
            raise ConditionError(f"unknown value {name} — use one of: " + ", ".join(sorted(ATTRIBUTES)))
        used.append(name)
    elif isinstance(node, ast.Constant):
        if not isinstance(node.value, (str, int, float, bool)):
            raise ConditionError(f"value {node.value!r} is not allowed")
    else:
        raise ConditionError(f"'{ast.unparse(node)}' is not allowed in a condition")


def _reserved(name: str) -> None:
    if name.split(".")[0] in RESERVED:
        raise ConditionError(f"{name} is reserved for 'adapt' (performance estimates), "
                             "which is not available yet")


def parse_condition(text: str) -> Tuple[ast.Expression, List[str]]:
    """Analyse une condition ; renvoie (arbre, fonctions et valeurs utilisées).
    Lève ConditionError avec un message lisible."""
    if not isinstance(text, str) or not text.strip():
        raise ConditionError("the condition is empty")
    src = _expand_units(text.strip())
    src = re.sub(r"\btrue\b", "True", re.sub(r"\bfalse\b", "False", src))
    try:
        tree = ast.parse(src, mode="eval")
    except SyntaxError as e:
        raise ConditionError(f"syntax error at column {e.offset or '?'}: {text.strip()}") from None
    used: List[str] = []
    _check(tree.body, used)
    return tree, used


def condition_sources(text: str) -> List[Tuple[str, str]]:
    """[(fonction, argument)] des appels d'une condition valide — pour vérifier
    au --dry-run que les sources / destinations / secrets nommés existent."""
    tree, _ = parse_condition(text)
    out: List[Tuple[str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            out.append((_dotted(node.func), node.args[0].value))
    return out
