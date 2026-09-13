"""
projection.py — quelles colonnes de la source le job lit-il vraiment ?

Le principe
-----------
Un job ETL déclare ses colonnes de sortie (`select`) ou ses agrégats
(`aggregate`). Tout ce qui n'y mène pas est lu, converti en chaîne, mis en
colonne pandas... pour rien. Sur une source de 40 colonnes dont 6 sont
utilisées, c'est 34 colonnes construites puis jetées.

Cette analyse remonte le pipeline à l'envers depuis la dernière opération
qui *fixe* les colonnes (`select` ou `aggregate`) et rend l'ensemble des
colonnes source nécessaires. Le lecteur ne construit alors que celles-là.

Prudence avant tout
-------------------
La fonction rend `None` — « lis tout », comportement d'avant — dès qu'un
doute existe :

- aucune opération ne fixe les colonnes (on ne sait pas ce qui sort) ;
- une opération dont l'effet dépend des colonnes présentes
  (`deduplicate` sans liste : retirer une colonne changerait les doublons) ;
- une opération opaque : `script`, `join`, `merge`, `union`, `pivot`,
  `unpivot`, `transpose` ;
- une expression que l'on ne sait pas analyser (`@variable`, backticks,
  appel de fonction) ;
- un `rename` dont l'inversion serait ambiguë.

Les opérations *après* la dernière qui fixe les colonnes n'ont pas besoin
d'être analysées : elles ne peuvent consommer que ce qui existe déjà à ce
point, donc rien de plus côté source.

Désactivation : HYDRA_PROJECTION=0.
"""

from __future__ import annotations

import ast
import logging
import os
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

_OFF = {"0", "false", "no", "off"}

# Opérations qui fixent entièrement les colonnes de sortie.
_TERMINAL_OPS = {"select", "aggregate"}

# Opérations opaques : on ne sait pas ce qu'elles lisent.
_OPAQUE_OPS = {"script", "join", "merge", "union", "pivot", "unpivot", "transpose"}


def projection_enabled() -> bool:
    return os.environ.get("HYDRA_PROJECTION", "1").strip().lower() not in _OFF


def _normalize(step: Any) -> Optional[Tuple[str, Dict[str, Any]]]:
    """(op, params) quel que soit le format du step, None si illisible."""
    if not isinstance(step, dict) or not step:
        return None
    if "op" in step:
        op, params = step.get("op"), step.get("params")
    else:
        op = next(iter(step))
        params = step[op]
    if not isinstance(op, str):
        return None
    return op.strip().lower(), (params if isinstance(params, dict) else {})


def _names_in_expr(expr: Any) -> Optional[Set[str]]:
    """Noms de colonnes cités par une expression, None si non analysable."""
    if not isinstance(expr, str) or not expr.strip():
        return None
    try:
        tree = ast.parse(expr.strip(), mode="eval")
    except SyntaxError:
        return None  # `@variable`, backticks, colonne au nom non-identifiant
    names: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            return None  # une fonction peut lire n'importe quoi
        if isinstance(node, ast.Attribute):
            return None
        if isinstance(node, ast.Name):
            names.add(node.id)
    return names


def _as_list(value: Any) -> Optional[List[str]]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return list(value)
    return None


def _terminal_columns(op: str, params: Dict[str, Any]) -> Optional[Set[str]]:
    """Colonnes exigées par l'opération qui fixe la sortie."""
    if op == "select":
        cols = _as_list(params.get("columns"))
        return set(cols) if cols else None
    # aggregate
    by = _as_list(params.get("by"))
    agg = params.get("agg")
    if not by or not isinstance(agg, dict):
        return None
    needed = set(by)
    for spec in agg.values():
        if not isinstance(spec, dict):
            return None
        col = spec.get("col")
        if not isinstance(col, str):
            return None
        needed.add(col)
    return needed


def required_columns(steps: List[Any]) -> Optional[Set[str]]:
    """Colonnes source nécessaires, ou None si l'on doit tout lire."""
    if not projection_enabled() or not steps:
        return None

    normalized: List[Tuple[str, Dict[str, Any]]] = []
    for step in steps:
        ns = _normalize(step)
        if ns is None:
            return None
        normalized.append(ns)

    # Dernière opération qui fixe les colonnes ; au-delà, rien de nouveau
    # n'est demandé à la source.
    last = -1
    for i, (op, _) in enumerate(normalized):
        if op in _TERMINAL_OPS:
            last = i
    if last < 0:
        return None

    op, params = normalized[last]
    needed = _terminal_columns(op, params)
    if needed is None:
        return None

    for op, params in reversed(normalized[:last]):
        if op in _OPAQUE_OPS:
            return None

        if op == "select":
            cols = _as_list(params.get("columns"))
            if cols is None:
                return None
            # les colonnes encore nécessaires viennent forcément de ce select
            continue

        if op == "rename":
            mapping = params.get("mapping")
            if not isinstance(mapping, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in mapping.items()
            ):
                return None
            inverse: Dict[str, str] = {}
            for old, new in mapping.items():
                if new in inverse:  # deux colonnes vers le même nom : ambigu
                    return None
                inverse[new] = old
            renamed = set()
            for c in needed:
                if c in inverse:
                    renamed.add(inverse[c])
                elif c in mapping:
                    # ce nom disparaît au rename et n'est pas recréé : ambigu
                    return None
                else:
                    renamed.add(c)
            needed = renamed
            continue

        if op == "cast":
            mapping = params.get("mapping")
            if not isinstance(mapping, dict):
                return None
            # cast échoue sur une colonne absente : elle doit être lue
            needed |= {k for k in mapping if isinstance(k, str)}
            continue

        if op == "filter":
            names = _names_in_expr(params.get("expr"))
            if names is None:
                return None
            needed |= names
            continue

        if op == "calculate":
            col = params.get("column")
            names = _names_in_expr(params.get("expr"))
            if names is None or not isinstance(col, str):
                return None
            needed.discard(col.strip())
            needed |= names
            continue

        if op == "sort":
            by = _as_list(params.get("by"))
            if by is None:
                return None
            needed |= set(by)
            continue

        if op == "deduplicate":
            cols = _as_list(params.get("columns"))
            if cols is None:
                # sans liste, le dédoublonnage porte sur TOUTES les colonnes :
                # en retirer changerait le résultat.
                return None
            needed |= set(cols)
            continue

        if op == "aggregate":
            cols = _terminal_columns("aggregate", params)
            if cols is None:
                return None
            needed = cols
            continue

        if op == "clean":
            cols = _as_list(params.get("columns"))
            if cols is not None:
                # clean échoue sur une colonne absente
                needed |= set(cols)
            continue

        if op in {"trim", "fill_null"}:
            # sans effet sur les autres colonnes, et tolérants aux absentes
            continue

        return None  # opération inconnue : prudence

    return needed or None
