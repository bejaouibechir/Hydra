"""
workflow/expr.py — Évaluation SÛRE d'expressions booléennes pour les conditions
de workflow (nœud Condition + garde `when` sur les steps).

Deux entrées :
  evaluate_bool(expr, params, env)               -> bool   (expression libre, mode A2)
  evaluate_structured(left, op, right, params, env) -> bool (mode A1 structuré)

Sécurité : l'expression libre est parsée en AST et évaluée avec une liste blanche
STRICTE de nœuds (comparaisons, and/or/not, littéraux, listes). AUCUN appel de
fonction, accès attribut, indexation, ni nom arbitraire : les `{{ param:X }}` /
`{{ env:X }}` sont remplacés AVANT parsing par des jetons dont la valeur vit dans
un namespace isolé. Impossible d'exécuter du code.
"""
from __future__ import annotations

import ast
import operator
import re
from typing import Any, Mapping

# {{ param:NAME }} / {{ env:NAME }}
_PLACEHOLDER_RE = re.compile(r"\{\{\s*(param|env)\s*:\s*([A-Za-z0-9_.\-]+)\s*\}\}")
_FULL_RE = re.compile(r"^\s*\{\{\s*(param|env)\s*:\s*([A-Za-z0-9_.\-]+)\s*\}\}\s*$")

_ALLOWED_NODES = (
    ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not,
    ast.USub, ast.UAdd, ast.Compare, ast.Name, ast.Load, ast.Constant,
    ast.List, ast.Tuple,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn,
)

_STRUCT_OPS = {
    "==": operator.eq, "!=": operator.ne,
    "<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge,
}


def _lookup(kind: str, name: str, params: Mapping[str, Any], env: Mapping[str, str]) -> Any:
    if kind == "env":
        return env.get(name, "")
    return params.get(name)  # None si absent


def _maybe_number(v: Any) -> Any:
    """Coerce une chaîne numérique en int/float ; laisse le reste tel quel."""
    if isinstance(v, bool) or not isinstance(v, str):
        return v
    s = v.strip()
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        return v


def _coerce_pair(a: Any, b: Any):
    """Si les deux ressemblent à des nombres, comparer en nombres."""
    na, nb = _maybe_number(a), _maybe_number(b)
    if isinstance(na, (int, float)) and not isinstance(na, bool) and \
       isinstance(nb, (int, float)) and not isinstance(nb, bool):
        return na, nb
    return a, b


# ── Expression libre (A2) ─────────────────────────────────────────────────────

def _tokenize(expr: str, params: Mapping[str, Any], env: Mapping[str, str]):
    """Remplace chaque placeholder par un jeton __vN et construit le namespace."""
    ns: dict[str, Any] = {}
    counter = {"i": 0}

    def repl(m: "re.Match[str]") -> str:
        tok = f"__v{counter['i']}"
        counter["i"] += 1
        ns[tok] = _lookup(m.group(1), m.group(2), params, env)
        return tok

    return _PLACEHOLDER_RE.sub(repl, expr), ns


def _eval_node(node: ast.AST, ns: Mapping[str, Any]) -> Any:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body, ns)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in ns:
            return ns[node.id]
        raise ValueError(f"nom non autorisé dans l'expression : '{node.id}'")
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_eval_node(e, ns) for e in node.elts]
    if isinstance(node, ast.BoolOp):
        vals = [_eval_node(v, ns) for v in node.values]
        return all(vals) if isinstance(node.op, ast.And) else any(vals)
    if isinstance(node, ast.UnaryOp):
        v = _eval_node(node.operand, ns)
        if isinstance(node.op, ast.Not):
            return not v
        if isinstance(node.op, ast.USub):
            return -v
        return +v
    if isinstance(node, ast.Compare):
        left = _eval_node(node.left, ns)
        for op, comp in zip(node.ops, node.comparators):
            right = _eval_node(comp, ns)
            if isinstance(op, ast.In):
                ok = left in right
            elif isinstance(op, ast.NotIn):
                ok = left not in right
            else:
                lc, rc = _coerce_pair(left, right)
                ok = _STRUCT_OPS[{ast.Eq: "==", ast.NotEq: "!=", ast.Lt: "<",
                                  ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">="}[type(op)]](lc, rc)
            if not ok:
                return False
            left = right
        return True
    raise ValueError(f"élément non autorisé dans l'expression : {type(node).__name__}")


def evaluate_bool(expr: str, params: Mapping[str, Any], env: Mapping[str, str]) -> bool:
    """Évalue une expression booléenne libre (sûre). Chaîne vide -> True (pas de garde)."""
    if expr is None or str(expr).strip() == "":
        return True
    tokenized, ns = _tokenize(str(expr), params, env)
    try:
        tree = ast.parse(tokenized, mode="eval")
    except SyntaxError as ex:
        raise ValueError(f"expression invalide : {ex}") from None
    for n in ast.walk(tree):
        if not isinstance(n, _ALLOWED_NODES):
            raise ValueError(f"expression non autorisée : {type(n).__name__}")
    return bool(_eval_node(tree, ns))


# ── Structuré (A1) ─────────────────────────────────────────────────────────────

def _resolve_operand(raw: Any, params: Mapping[str, Any], env: Mapping[str, str]) -> Any:
    """Résout un opérande : placeholder plein -> valeur typée ; sinon littéral."""
    if not isinstance(raw, str):
        return raw
    m = _FULL_RE.match(raw)
    if m:
        return _lookup(m.group(1), m.group(2), params, env)
    # substitution des placeholders intégrés, puis littéral
    sub = _PLACEHOLDER_RE.sub(lambda mm: str(_lookup(mm.group(1), mm.group(2), params, env) or ""), raw)
    return sub


def evaluate_structured(left: Any, op: str, right: Any,
                        params: Mapping[str, Any], env: Mapping[str, str]) -> bool:
    """Compare left <op> right. op ∈ {==,!=,<,<=,>,>=,contains}."""
    lv = _resolve_operand(left, params, env)
    rv = _resolve_operand(right, params, env)
    if op == "contains":
        try:
            return str(rv) in lv if isinstance(lv, (list, tuple, dict, set)) else str(rv) in str(lv)
        except TypeError:
            return False
    if op not in _STRUCT_OPS:
        raise ValueError(f"opérateur inconnu : '{op}'")
    lc, rc = _coerce_pair(lv, rv)
    try:
        return bool(_STRUCT_OPS[op](lc, rc))
    except TypeError:
        # types incomparables -> comparer en chaînes (sauf égalité)
        return bool(_STRUCT_OPS[op](str(lc), str(rc)))
