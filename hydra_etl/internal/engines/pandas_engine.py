#!/usr/bin/env python
"""
Engine Pandas (MVP) - Version Corrigée

Règles strictes :
- Aucune exception Pandas / Python ne fuit
- Tout est normalisé en ValueError avec message clair
- Validation stricte des paramètres d'entrée
- Support des 5 opérations MVP : select, rename, cast, filter, calculate

Corrections appliquées :
- Suppression du paramètre context (non utilisé en MVP)
- Type hints stricts sur apply_pipeline
- Validation des params plus stricte
- Déduplication automatique des colonnes dans select
- Rejection des pipelines vides
"""

from __future__ import annotations

import ast
import builtins as _bi
import contextlib
import io
import logging
import math
import re
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from hydra_etl.internal.engines.expr_engine import choose_expr_engine
from hydra_etl.internal.engines.frame_copy import lazy_copy
from hydra_etl.internal.transform.engine_interface import StepResult, TransformEngine

logger = logging.getLogger(__name__)

# Verrou pour la capture stdout des scripts (evite le melange entre
# jobs paralleles — sys.stdout est global au processus)
_SCRIPT_STDOUT_LOCK = threading.Lock()


def _emit_script_output(buf: io.StringIO) -> None:
    """Reroute les print() du script utilisateur vers le logger
    (visibles dans les logs du run Studio/CLI)."""
    text = buf.getvalue()
    if not text:
        return
    for line in text.splitlines():
        logger.info(f"script> {line}")



_IS_NULL = re.compile(r"(`[^`]+`|\b[A-Za-z_]\w*)\s+is\s+(not\s+)?null\b", re.I)


def _sql_null_tests(expr: str) -> str:
    """`price is not null` / `price is null`, as written in SQL -> .notna() / .isna()."""
    if "null" not in expr.lower():
        return expr
    return _IS_NULL.sub(lambda m: f"{m.group(1)}.{'notna' if m.group(2) else 'isna'}()", expr)


class _RoundCalls(ast.NodeTransformer):
    """Replaces each round(x, n) with a temporary column (pandas eval has no round())."""

    def __init__(self) -> None:
        self.temps: List[tuple] = []

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        if (isinstance(node.func, ast.Name) and node.func.id == "round"
                and 1 <= len(node.args) <= 2 and not node.keywords):
            nd = node.args[1] if len(node.args) == 2 else ast.Constant(0)
            if isinstance(nd, ast.Constant) and isinstance(nd.value, int):
                name = f"__hydra_round_{len(self.temps)}"
                self.temps.append((name, ast.unparse(node.args[0]), nd.value))
                return ast.Name(id=name, ctx=ast.Load())
        return node


def _split_round(expr: str):
    """Lets calculate accept round(revenue, 2), as written in Python or SQL.

    Returns (expr, temps): each temp is (column, inner expression, digits),
    computed before the expression and dropped after.
    """
    if "round" not in expr:
        return expr, []
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return expr, []
    t = _RoundCalls()
    tree = t.visit(tree)
    if not t.temps:
        return expr, []
    return ast.unparse(ast.fix_missing_locations(tree)), t.temps


# --------------------------------------------------
# Sandbox pour l'operation 'script' (code Python user)
# --------------------------------------------------

# Noms interdits (evasion / effets de bord)
_SCRIPT_FORBIDDEN_NAMES = frozenset({
    "__import__", "eval", "exec", "compile", "open", "input",
    "globals", "locals", "vars", "getattr", "setattr", "delattr",
    "memoryview", "breakpoint", "help", "exit", "quit", "__build_class__",
})

# Builtins autorises dans le code utilisateur
_SCRIPT_ALLOWED_BUILTINS = frozenset({
    "abs", "round", "min", "max", "sum", "len", "int", "float", "str",
    "bool", "list", "dict", "tuple", "set", "sorted", "reversed", "zip",
    "range", "enumerate", "map", "filter", "any", "all", "divmod", "pow",
    "isinstance", "print", "format", "repr", "ord", "chr", "hex", "bin",
    "True", "False", "None",
})

_SCRIPT_SAFE_BUILTINS: Dict[str, Any] = {
    n: getattr(_bi, n) for n in _SCRIPT_ALLOWED_BUILTINS if hasattr(_bi, n)
}


def _validate_script_ast(code: str) -> None:
    """Rejette import, dunder et appels dangereux avant execution."""
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as e:
        raise ValueError(f"script: syntax error: {e}") from None

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise ValueError("script: 'import' interdit dans le code")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise ValueError(
                f"script: acces a l'attribut '{node.attr}' interdit"
            )
        if isinstance(node, ast.Name) and node.id in _SCRIPT_FORBIDDEN_NAMES:
            raise ValueError(f"script: usage de '{node.id}' interdit")


def _script_globals() -> Dict[str, Any]:
    """Namespace global fige expose au code utilisateur."""
    return {
        "__builtins__": dict(_SCRIPT_SAFE_BUILTINS),
        "pd": pd,
        "np": np,
        "math": math,
        "re": re,
    }


def _coerce_output(series: pd.Series, typ: str, col: str = "") -> pd.Series:
    """Coercition legere d'une colonne de sortie selon le type declare."""
    t = (typ or "any").lower()
    if t == "any":
        return series
    try:
        if t == "int":
            return pd.to_numeric(series, errors="raise").astype("Int64")
        if t == "float":
            return pd.to_numeric(series, errors="raise").astype("float64")
        if t == "str":
            return series.astype("string")
        if t == "bool":
            return series.astype("bool")
        if t.startswith("date"):
            return pd.to_datetime(series, errors="raise")
    except Exception as ex:
        raise ValueError(
            f"script: output column '{col}' cannot be converted to '{typ}' "
            f"(example value: {series.iloc[0]!r}): {ex}"
        ) from None
    return series


@dataclass(frozen=True)
class _NormalizedStep:
    """Structure interne normalisée d'une étape de transformation."""

    op: str
    params: Dict[str, Any]


class PandasEngine(TransformEngine):
    """
    Moteur de transformation basé sur Pandas.

    Supporte les opérations MVP :
    - select : sélection de colonnes (avec déduplication)
    - rename : renommage de colonnes
    - cast : conversion de types (int, float, str, bool, datetime)
    - filter : filtrage par expression
    - calculate : calcul de nouvelles colonnes

    Toutes les erreurs sont normalisées en ValueError avec contexte.
    """

    def __init__(self, name: str = "pandas") -> None:
        super().__init__(name=name)

    # --------------------------------------------------
    # API TransformEngine
    # --------------------------------------------------

    def apply_step(
        self,
        dataset: Any,
        step: Dict[str, Any],
        *,
        context: Optional[Dict[str, Any]] = None,
    ) -> StepResult:
        """
        Applique une transformation unique sur un DataFrame Pandas.

        Args:
            dataset: DataFrame Pandas à transformer
            step: Définition de l'étape (format normalisé ou DSL)
                  Ex: {"op": "select", "params": {"columns": [...]}}
                  Ex: {"select": {"columns": [...]}}
            context: Infos runtime optionnelles (job_id, paramètres, etc.) — non utilisé MVP

        Returns:
            StepResult avec dataset transformé et statistiques

        Raises:
            ValueError: Si dataset n'est pas un DataFrame ou si l'opération échoue
        """
        if not isinstance(dataset, pd.DataFrame):
            raise ValueError(
                f"PandasEngine expects a pandas.DataFrame, got {type(dataset).__name__}"
            )

        ns = self._normalize_step(step)

        rows_in, cols_in = dataset.shape
        df_out = self._apply_op(dataset, ns)
        rows_out, cols_out = df_out.shape

        return StepResult(
            output=df_out,
            stats={
                "engine": self.name,
                "op": ns.op,
                "rows_in": rows_in,
                "rows_out": rows_out,
                "cols_in": cols_in,
                "cols_out": cols_out,
                "rows_filtered": rows_in - rows_out,
            },
        )

    def apply_pipeline(
        self,
        dataset: Any,
        steps: List[Dict[str, Any]],
        *,
        context: Optional[Dict[str, Any]] = None,
    ) -> StepResult:
        """
        Applique une séquence de transformations sur un DataFrame.

        Args:
            dataset: DataFrame Pandas initial
            steps: Liste d'étapes de transformation
            context: Infos runtime optionnelles transmises à chaque apply_step

        Returns:
            StepResult dont .output est le DataFrame final transformé

        Raises:
            ValueError: Si la liste d'étapes est vide ou si une étape échoue
        """
        if not steps:
            raise ValueError("Empty pipeline: at least one transformation is required")

        if not isinstance(steps, list):
            raise ValueError(
                f"steps must be a list, got {type(steps).__name__}"
            )

        df = dataset
        all_stats: list = []
        for idx, step in enumerate(steps, start=1):
            try:
                result = self.apply_step(df, step, context=context)
                df = result.output
                all_stats.append({"index": idx, "stats": result.stats})
            except ValueError as e:
                raise ValueError(f"Step {idx}/{len(steps)}: {e}") from None

        return StepResult(output=df, stats={"steps": all_stats})

    # --------------------------------------------------
    # Internals
    # --------------------------------------------------

    def _normalize_step(self, step: Dict[str, Any]) -> _NormalizedStep:
        """
        Normalise une étape dans le format interne.

        Supporte 2 formats :
        - {"op": "select", "params": {...}}
        - {"select": {...}}
        """
        if not isinstance(step, dict):
            raise ValueError(f"A step must be a mapping, got {type(step).__name__}")

        # Format normalisé : {"op": ..., "params": ...}
        if "op" in step:
            op = step["op"]
            if not isinstance(op, str):
                raise ValueError(f"op must be a string, got {type(op).__name__}")

            return _NormalizedStep(
                op=op.lower(),
                params=step.get("params", {}),
            )

        # Format DSL : {"select": {...}}
        if len(step) != 1:
            raise ValueError(
                f"Invalid step: it must have exactly 1 key (the operation), found {len(step)}"
            )

        op = next(iter(step))
        params = step[op]

        if not isinstance(params, dict):
            raise ValueError(
                f"The parameters of '{op}' must be a mapping, got {type(params).__name__}"
            )

        return _NormalizedStep(op=op.lower(), params=params)

    def _apply_op(self, df: pd.DataFrame, step: _NormalizedStep) -> pd.DataFrame:
        """Dispatche l'opération vers la méthode appropriée."""
        if step.op == "select":
            return self._op_select(df, step.params)
        if step.op == "rename":
            return self._op_rename(df, step.params)
        if step.op == "cast":
            return self._op_cast(df, step.params)
        if step.op == "filter":
            return self._op_filter(df, step.params)
        if step.op == "calculate":
            return self._op_calculate(df, step.params)
        if step.op == "sort":
            return self._op_sort(df, step.params)
        if step.op == "deduplicate":
            return self._op_deduplicate(df, step.params)
        if step.op == "fill_null":
            return self._op_fill_null(df, step.params)
        if step.op == "trim":
            return self._op_trim(df, step.params)
        if step.op == "aggregate":
            return self._op_aggregate(df, step.params)
        if step.op == "join":
            return self._op_join(df, step.params)
        if step.op == "clean":
            return self._op_clean(df, step.params)
        if step.op == "pivot":
            return self._op_pivot(df, step.params)
        if step.op == "unpivot":
            return self._op_unpivot(df, step.params)
        if step.op == "transpose":
            return self._op_transpose(df, step.params)
        if step.op == "merge":
            return self._op_merge(df, step.params)
        if step.op == "union":
            return self._op_union(df, step.params)
        if step.op == "script":
            return self._op_script(df, step.params)
        if step.op == "text_to_rows":
            return self._op_text_to_rows(df, step.params)
        if step.op == "window":
            from hydra_etl.internal.engines.window import apply_pandas
            return apply_pandas(df, step.params)

        raise ValueError(
            f"Unknown operation: {step.op}. "
            f"Available operations: select, rename, cast, filter, calculate, sort, deduplicate, fill_null, trim, aggregate, join, clean, pivot, unpivot, transpose, merge, union, script, text_to_rows, window"
        )

    # --------------------------------------------------
    # Operations MVP
    # --------------------------------------------------

    def _op_select(self, df: pd.DataFrame, p: Dict[str, Any]) -> pd.DataFrame:
        """
        Sélectionne les colonnes spécifiées.

        Params:
            columns: List[str] - colonnes à garder (dédupliquées automatiquement)
        """
        cols = p.get("columns")

        if not cols:
            raise ValueError("select.columns is required and cannot be empty")

        if not isinstance(cols, list):
            raise ValueError(
                f"select.columns must be a list, got {type(cols).__name__}"
            )

        if not all(isinstance(c, str) for c in cols):
            raise ValueError("select.columns must contain strings only")

        # Déduplication tout en préservant l'ordre
        cols = list(dict.fromkeys(cols))

        missing = [c for c in cols if c not in df.columns]
        if missing:
            raise ValueError(
                f"select: unknown columns {missing}. "
                f"Available columns: {list(df.columns)}"
            )

        return lazy_copy(df.loc[:, cols])

    def _op_rename(self, df: pd.DataFrame, p: Dict[str, Any]) -> pd.DataFrame:
        """
        Renomme des colonnes.

        Params:
            mapping: Dict[str, str] - {"old_name": "new_name"}
        """
        mapping = p.get("mapping")

        if not mapping:
            raise ValueError("rename.mapping is required and cannot be empty")

        if not isinstance(mapping, dict):
            raise ValueError(
                f"rename.mapping must be a mapping, got {type(mapping).__name__}"
            )

        missing = [c for c in mapping.keys() if c not in df.columns]
        if missing:
            raise ValueError(
                f"rename: unknown columns {missing}. "
                f"Available columns: {list(df.columns)}"
            )

        return df.rename(columns=mapping)

    def _op_cast(self, df: pd.DataFrame, p: Dict[str, Any]) -> pd.DataFrame:
        """
        Convertit le type de colonnes.

        Params:
            mapping: Dict[str, str] - {"column": "type"}
            Types supportés: int, integer, float, str, string, bool, boolean, datetime
        """
        mapping = p.get("mapping")

        if not mapping:
            raise ValueError("cast.mapping is required and cannot be empty")

        if not isinstance(mapping, dict):
            raise ValueError(
                f"cast.mapping must be a mapping, got {type(mapping).__name__}"
            )

        out = lazy_copy(df)

        for col, typ in mapping.items():
            if col not in out.columns:
                raise ValueError(
                    f"cast: unknown column '{col}'. "
                    f"Available columns: {list(out.columns)}"
                )

            if not isinstance(typ, str):
                raise ValueError(
                    f"cast: the type of '{col}' must be a string, got {type(typ).__name__}"
                )

            t = typ.lower()

            try:
                if t in {"int", "integer"}:
                    out[col] = self._to_numeric_fast(out[col], "Int64")

                elif t == "float":
                    out[col] = self._to_numeric_fast(out[col], "float64")

                elif t in {"str", "string"}:
                    out[col] = out[col].astype("string")

                elif t in {"bool", "boolean"}:
                    out[col] = self._cast_to_bool(out[col])

                elif t.startswith("datetime"):
                    out[col] = pd.to_datetime(out[col], errors="raise")

                else:
                    raise ValueError(
                        f"Unsupported type: '{typ}'. "
                        f"Available types: int, float, str, bool, datetime"
                    )

            except ValueError as e:
                # Re-raise ValueError avec contexte ajouté
                if "Type non supporté" in str(e):
                    raise
                raise ValueError(
                    f"cast: cannot convert column='{col}' to type='{typ}': {e}"
                ) from None
            except Exception as e:
                raise ValueError(
                    f"cast: cannot convert column='{col}' to type='{typ}': {e}"
                ) from None

        return out

    def _op_filter(self, df: pd.DataFrame, p: Dict[str, Any]) -> pd.DataFrame:
        """
        Filtre les lignes selon une expression.

        Params:
            expr: str - expression Python/Pandas (ex: "age > 18 and city == 'Paris'")
        """
        expr = p.get("expr")

        if not expr:
            raise ValueError("filter.expr is required and cannot be empty")

        if not isinstance(expr, str):
            raise ValueError(
                f"filter.expr must be a string, got {type(expr).__name__}"
            )

        expr = expr.strip()
        if not expr:
            raise ValueError("filter.expr cannot be an empty string")
        expr = _sql_null_tests(expr)

        engine = choose_expr_engine(df, expr)
        if engine != "python":
            try:
                return lazy_copy(df.query(expr, engine=engine))
            except Exception:
                pass  # repli : le moteur d'origine tranche, message compris
        try:
            return lazy_copy(df.query(expr, engine="python"))
        except Exception as e:
            raise ValueError(
                f"filter: invalid expression '{expr}'. Error: {e}"
            ) from None

    def _op_union(self, df: pd.DataFrame, p: Dict[str, Any]) -> pd.DataFrame:
        """
        Union / Union All : empile une 2e source (prechargee dans p["_right_rows"]).
        distinct=False -> UNION ALL (garde tout) ; distinct=True -> UNION (dedoublonne).
        """
        right_rows = p.get("_right_rows")
        if right_rows is None:
            raise ValueError("union: source not loaded (the step must run through the job runner).")
        distinct = bool(p.get("distinct", False))
        other = pd.DataFrame(list(right_rows))
        result = pd.concat([df, other], ignore_index=True, sort=False)
        if distinct:
            result = result.drop_duplicates()
        return result.reset_index(drop=True)

    def _op_script(self, df: pd.DataFrame, p: Dict[str, Any]) -> pd.DataFrame:
        """
        Transformation Python personnalisee (facon SSIS Script Component).

        Contrat : inputs (colonnes lues) -> outputs (colonnes produites).
        Le code s'execute dans un environnement restreint (pas d'import, pas
        d'acces fichiers/reseau, builtins whitelistes).

        Params:
            inputs: List[str]         - colonnes exposees au code
            outputs: Dict[str, str]   - {nom_colonne: type} produites par le code
            code: str                 - corps Python
            mode: 'vectorized'|'row'  - Series entieres vs ligne par ligne

        Modes:
        - vectorized : chaque input est une pandas.Series ; le code doit
                       affecter chaque output (Series ou scalaire broadcaste).
        - row        : le code s'execute par ligne ; chaque input est un
                       scalaire, chaque output un scalaire.
        """
        inputs = p.get("inputs") or []
        outputs = p.get("outputs") or {}
        code = p.get("code")
        mode = str(p.get("mode", "vectorized")).lower()

        if not isinstance(inputs, list):
            raise ValueError("script.inputs must be a list of columns")
        if not isinstance(outputs, dict) or not outputs:
            raise ValueError("script.outputs is required (a non-empty mapping {column: type})")
        if not code or not isinstance(code, str):
            raise ValueError("script.code is required (a non-empty string)")
        if mode not in ("vectorized", "row"):
            raise ValueError(f"script.mode invalid: {mode} (vectorized|row)")

        missing = [c for c in inputs if c not in df.columns]
        if missing:
            raise ValueError(
                f"script: unknown input columns {missing}. "
                f"Available columns: {list(df.columns)}"
            )

        _validate_script_ast(code)
        try:
            compiled = compile(code, "<hydra-script>", "exec")
        except Exception as ex:
            raise ValueError(f"script: cannot compile: {ex}") from None

        g = _script_globals()
        g["params"] = dict(p.get("_params") or {})  # parametres (lecture seule)
        out = lazy_copy(df)

        if mode == "vectorized":
            local_ns: Dict[str, Any] = {c: out[c] for c in inputs}
            _buf = io.StringIO()
            try:
                with _SCRIPT_STDOUT_LOCK, contextlib.redirect_stdout(_buf):
                    exec(compiled, g, local_ns)  # noqa: S102 - sandbox controle
            except Exception as ex:
                _emit_script_output(_buf)
                raise ValueError(f"script: runtime error: {ex}") from None
            _emit_script_output(_buf)
            for col, typ in outputs.items():
                if col not in local_ns:
                    raise ValueError(
                        f"script: output column '{col}' is not set by the code"
                    )
                out[col] = _coerce_output(pd.Series(local_ns[col], index=out.index), typ, col)
            return out

        # mode == "row"
        collected: Dict[str, list] = {col: [] for col in outputs}
        _buf = io.StringIO()
        try:
            with _SCRIPT_STDOUT_LOCK, contextlib.redirect_stdout(_buf):
                for _, row in out.iterrows():
                    local_ns = {c: row[c] for c in inputs}
                    try:
                        exec(compiled, g, local_ns)  # noqa: S102 - sandbox controle
                    except Exception as ex:
                        raise ValueError(f"script: runtime error (row mode): {ex}") from None
                    for col in outputs:
                        if col not in local_ns:
                            raise ValueError(
                                f"script: output column '{col}' is not set by the code"
                            )
                        collected[col].append(local_ns[col])
        finally:
            _emit_script_output(_buf)
        for col, typ in outputs.items():
            out[col] = _coerce_output(pd.Series(collected[col], index=out.index), typ, col)
        return out

    def _op_merge(self, df: pd.DataFrame, p: Dict[str, Any]) -> pd.DataFrame:
        """
        Merge type SQL Server (upsert). df = cible ; la source est prechargee dans
        p["_right_rows"] par le runner.
        - cle appariee -> valeurs de la source (update)
        - cle seulement dans la source -> inseree
        - cle seulement dans la cible -> conservee (ou supprimee si delete_unmatched)
        Params: key, delete_unmatched.
        """
        right_rows = p.get("_right_rows")
        if right_rows is None:
            raise ValueError("merge: source not loaded (the step must run through the job runner).")
        key = p.get("key")
        if not key:
            raise ValueError("merge.key is required (the matching key)")
        keys = [key] if isinstance(key, str) else list(key)
        delete_unmatched = bool(p.get("delete_unmatched", False))
        source_df = pd.DataFrame(list(right_rows))
        for k in keys:
            if k not in df.columns:
                raise ValueError(f"merge: key '{k}' missing from the target")
            if k not in source_df.columns:
                raise ValueError(f"merge: key '{k}' missing from the source")
        combined = pd.concat([df, source_df], ignore_index=True, sort=False)
        result = combined.drop_duplicates(subset=keys, keep="last")
        if delete_unmatched:
            src_keys = set(source_df[keys].apply(tuple, axis=1))
            result = result[result[keys].apply(tuple, axis=1).isin(src_keys)]
        return result.reset_index(drop=True)

    def _op_transpose(self, df: pd.DataFrame, p: Dict[str, Any]) -> pd.DataFrame:
        """
        Transpose lignes <-> colonnes.
        Params: index_col (colonne dont les valeurs deviennent les en-tetes),
                header_name (nom de la colonne des anciens en-tetes, defaut 'column').
        """
        idx = p.get("index_col")
        header_name = p.get("header_name") or "column"
        out = lazy_copy(df)
        if idx:
            if idx not in out.columns:
                raise ValueError(f"transpose: unknown index_col '{idx}'. Available columns: {list(out.columns)}")
            out = out.set_index(idx)
        t = out.T
        t.index.name = header_name
        return t.reset_index()

    def _op_clean(self, df: pd.DataFrame, p: Dict[str, Any]) -> pd.DataFrame:
        """
        Nettoie les colonnes texte : reduit les espaces (trim + espaces multiples)
        et normalise la casse. Params: columns (defaut toutes texte), case (none|lower|upper).
        """
        import re
        cols = p.get("columns")
        case = str(p.get("case", "none")).lower()
        out = lazy_copy(df)
        targets = cols if cols else [c for c in out.columns if out[c].dtype == object]
        for c in targets:
            if c not in out.columns:
                raise ValueError(f"clean: unknown column '{c}'. Available columns: {list(out.columns)}")

            def _cl(v):
                if not isinstance(v, str):
                    return v
                v = re.sub(r"\s+", " ", v).strip()
                if case == "lower":
                    return v.lower()
                if case == "upper":
                    return v.upper()
                return v

            out[c] = out[c].map(_cl)
        return out

    def _op_pivot(self, df: pd.DataFrame, p: Dict[str, Any]) -> pd.DataFrame:
        """
        Pivot long -> large (pandas pivot_table).
        Params: index (liste), columns (str), values (str), aggfunc (defaut 'first').
        """
        index = p.get("index")
        column = p.get("column")
        values = p.get("values")
        aggfunc = p.get("aggfunc", "first")
        if not index or not column or not values:
            raise ValueError("pivot requiert 'index' (liste), 'column' (str) et 'values' (str)")
        if isinstance(index, str):
            index = [index]
        try:
            res = pd.pivot_table(df, index=index, columns=column, values=values, aggfunc=aggfunc)
            res = res.reset_index()
            res.columns = [
                "_".join(str(x) for x in c if x != "") if isinstance(c, tuple) else str(c)
                for c in res.columns
            ]
            return res.reset_index(drop=True)
        except Exception as e:
            raise ValueError(f"pivot: {e}") from None

    def _op_unpivot(self, df: pd.DataFrame, p: Dict[str, Any]) -> pd.DataFrame:
        """
        Unpivot large -> long (pandas melt).
        Params: id_vars (liste), value_vars (liste, defaut le reste), var_name, value_name.
        """
        id_vars = p.get("id_vars", [])
        value_vars = p.get("value_vars")
        var_name = p.get("var_name", "variable")
        value_name = p.get("value_name", "value")
        if isinstance(id_vars, str):
            id_vars = [id_vars]
        if isinstance(value_vars, str):
            value_vars = [value_vars]
        try:
            return df.melt(
                id_vars=id_vars or None,
                value_vars=value_vars or None,
                var_name=var_name,
                value_name=value_name,
            )
        except Exception as e:
            raise ValueError(f"unpivot: {e}") from None

    def _op_join(self, df: pd.DataFrame, p: Dict[str, Any]) -> pd.DataFrame:
        """
        Jointure avec une source de reference.

        Le runner precharge les lignes de la source droite dans p["_right_rows"].
        Params: on (str|list), how (inner|left|right|outer).
        """
        right_rows = p.get("_right_rows")
        if right_rows is None:
            raise ValueError(
                "join: reference source not loaded. "
                "The 'join' step must run through the job runner (a 'right' source is required)."
            )
        how = p.get("how", "inner")
        if how not in ("inner", "left", "right", "outer", "cross"):
            raise ValueError(f"join.how invalid: {how} (inner|left|right|outer|cross)")
        right_df = pd.DataFrame(list(right_rows))
        if how == "cross":
            return self._cross_join(df, right_df, p)

        left_key = p.get("left_key")
        right_key = p.get("right_key")
        if left_key and right_key:
            # Cles distinctes (self-join, ou FK != PK)
            lk = [left_key] if isinstance(left_key, str) else list(left_key)
            rk = [right_key] if isinstance(right_key, str) else list(right_key)
            for k in lk:
                if k not in df.columns:
                    raise ValueError(f"join: left_key '{k}' absente du flux gauche")
            for k in rk:
                if k not in right_df.columns:
                    raise ValueError(f"join: right_key '{k}' absente de la source de reference")
            return df.merge(right_df, left_on=lk, right_on=rk, how=how, suffixes=("", "_r"))

        key = p.get("key")
        if not key:
            raise ValueError("join: 'key' (or 'left_key' + 'right_key') is required")
        keys = [key] if isinstance(key, str) else list(key)
        for k in keys:
            if k not in df.columns:
                raise ValueError(f"join: key '{k}' missing from the left side")
            if k not in right_df.columns:
                raise ValueError(f"join: key '{k}' missing from the reference source")
        return df.merge(right_df, on=keys, how=how, suffixes=("", "_r"))

    # Garde-fou du produit cartésien : lignes produites au plus (forçable par max_rows)
    CROSS_MAX_ROWS = 10_000_000

    def _cross_join(self, df: pd.DataFrame, right_df: pd.DataFrame, p: Dict[str, Any]) -> pd.DataFrame:
        """Produit cartésien : chaque ligne du flux × chaque ligne de droite, dans
        l'ordre (gauche, puis droite). Ligne à ligne : appliqué lot par lot, même
        résultat. Le total produit, cumulé sur les lots (p["_cross_rows"]), est
        vérifié AVANT de produire le lot qui dépasserait max_rows."""
        given = [k for k in ("key", "left_key", "right_key") if p.get(k)]
        if given:
            raise ValueError(f"join: how: cross takes no key — remove {', '.join(given)}")
        limit = p.get("max_rows") or self.CROSS_MAX_ROWS
        total = int(p.get("_cross_rows", 0)) + len(df) * len(right_df)
        if total > limit:
            raise ValueError(
                f"join (cross): {total:,} rows would be produced, more than max_rows ({limit:,}). "
                f"Filter the inputs first, or raise join.max_rows if this size is intended")
        p["_cross_rows"] = total
        if right_df.shape[1] == 0:            # source de droite vide, sans colonnes
            return df.iloc[:0].copy()
        return df.merge(right_df, how="cross", suffixes=("", "_r"))

    def _op_calculate(self, df: pd.DataFrame, p: Dict[str, Any]) -> pd.DataFrame:
        """
        Calcule une nouvelle colonne à partir d'une expression.

        Params:
            column: str - nom de la nouvelle colonne
            expr: str - expression de calcul (ex: "price * quantity")

        Note: Si la colonne existe déjà, elle sera écrasée.
        """
        col = p.get("column")
        expr = p.get("expr")

        if not col:
            raise ValueError("calculate.column is required and cannot be empty")

        if not expr:
            raise ValueError("calculate.expr is required and cannot be empty")

        if not isinstance(col, str):
            raise ValueError(
                f"calculate.column must be a string, got {type(col).__name__}"
            )

        if not isinstance(expr, str):
            raise ValueError(
                f"calculate.expr must be a string, got {type(expr).__name__}"
            )

        col = col.strip()
        expr = expr.strip()

        if not col:
            raise ValueError("calculate.column cannot be an empty string")

        if not expr:
            raise ValueError("calculate.expr cannot be an empty string")

        expr, temps = _split_round(expr)
        if temps:
            out = lazy_copy(df)
            try:
                for name, inner, nd in temps:
                    out[name] = pd.to_numeric(out.eval(inner, engine="python")).round(nd)
                out[col] = out.eval(expr, engine="python")
            except Exception as e:
                raise ValueError(
                    f"calculate: invalid expression '{p.get('expr')}'. Error: {e}"
                ) from None
            return out.drop(columns=[n for n, _, _ in temps if n != col])

        engine = choose_expr_engine(df, expr)
        out = lazy_copy(df)
        if engine != "python":
            try:
                out[col] = out.eval(expr, engine=engine)
                return out
            except Exception:
                out = lazy_copy(df)  # repli propre
        try:
            out[col] = out.eval(expr, engine="python")
        except Exception as e:
            raise ValueError(
                f"calculate: invalid expression '{expr}'. Error: {e}"
            ) from None

        return out

    def _op_sort(self, df: pd.DataFrame, p: Dict[str, Any]) -> pd.DataFrame:
        """
        Trie le DataFrame.

        Params:
            by: List[str] - colonnes de tri
            ascending: bool | List[bool] - ordre (defaut True)

        Tri stable : à égalité, les lignes gardent leur ordre d'arrivée (résultat
        déterministe, identique avec le moteur gros volumes).
        """
        by = p.get("by")
        if not by:
            raise ValueError("sort.by is required (a list of columns)")
        if isinstance(by, str):
            by = [by]
        ascending = p.get("ascending", True)
        return df.sort_values(by=by, ascending=ascending, kind="stable").reset_index(drop=True)

    def _op_deduplicate(self, df: pd.DataFrame, p: Dict[str, Any]) -> pd.DataFrame:
        """
        Supprime les doublons.

        Params:
            columns: List[str] - colonnes de reference (optionnel, defaut toutes)
            keep: 'first' | 'last' (defaut 'first')
        """
        cols = p.get("columns") or None
        keep = p.get("keep", "first")
        return df.drop_duplicates(subset=cols, keep=keep).reset_index(drop=True)

    def _op_fill_null(self, df: pd.DataFrame, p: Dict[str, Any]) -> pd.DataFrame:
        """
        Remplace les valeurs nulles.

        Params:
            value: valeur de remplacement (s'applique a tout le DataFrame)
            columns: dict {col: valeur} pour un remplacement par colonne
        """
        columns = p.get("columns")
        if columns and isinstance(columns, dict):
            return df.fillna(columns)
        value = p.get("value")
        if value is None:
            raise ValueError("fill_null requiert 'value' ou 'columns' (dict)")
        return df.fillna(value)

    def _op_text_to_rows(self, df: pd.DataFrame, p: Dict[str, Any]) -> pd.DataFrame:
        """
        Une ligne par valeur : "a;b;c" -> 3 lignes, les autres colonnes recopiées.

        Params: column, sep (défaut ","), regex, trim (défaut True),
        keep_empty (défaut False), index_column (position 1, 2, 3...).
        Valeur nulle -> une ligne, nulle (position nulle). Aucune valeur non
        vide -> une ligne, nulle : une ligne d'entrée n'est jamais perdue.
        Ligne à ligne : appliqué lot par lot, même résultat.
        """
        import re
        col = p.get("column")
        if not isinstance(col, str) or not col:
            raise ValueError("text_to_rows: 'column' is required")
        if col not in df.columns:
            raise ValueError(f"text_to_rows: column '{col}' not found (available: {', '.join(map(str, df.columns))})")
        sep = p.get("sep", ",")
        if not isinstance(sep, str) or sep == "":
            raise ValueError("text_to_rows: 'sep' cannot be empty")
        idx_col = p.get("index_column")
        if idx_col is not None and (idx_col == col or idx_col in df.columns):
            raise ValueError(f"text_to_rows: index_column '{idx_col}' already exists")
        trim = bool(p.get("trim", True))
        keep_empty = bool(p.get("keep_empty", False))
        split = re.compile(sep).split if p.get("regex") else (lambda s: s.split(sep))

        values: List[Any] = []
        positions: List[Any] = []
        counts: List[int] = []
        for v in df[col].tolist():
            if v is None or (not isinstance(v, (list, dict)) and pd.isna(v)):
                values.append(None); positions.append(None); counts.append(1)
                continue
            items = split(v if isinstance(v, str) else str(v))
            if trim:
                items = [x.strip() for x in items]
            if not keep_empty:
                items = [x for x in items if x != ""]
            if not items:
                values.append(None); positions.append(None); counts.append(1)
                continue
            values.extend(items)
            positions.extend(range(1, len(items) + 1))
            counts.append(len(items))

        out = df.loc[df.index.repeat(counts)].reset_index(drop=True)
        dtype = df[col].dtype if pd.api.types.is_string_dtype(df[col].dtype) \
            and not pd.api.types.is_object_dtype(df[col].dtype) else object
        out[col] = pd.Series(values, dtype=dtype)
        if idx_col is not None:
            pos = list(out.columns).index(col) + 1
            out.insert(pos, idx_col, pd.Series(positions, dtype="Int64"))
        return out

    def _op_trim(self, df: pd.DataFrame, p: Dict[str, Any]) -> pd.DataFrame:
        """
        Supprime les espaces superflus sur les colonnes string.

        Params:
            columns: List[str] - colonnes a trimmer (defaut : toutes les colonnes string)
        """
        cols = p.get("columns")
        out = lazy_copy(df)
        if cols:
            for c in cols:
                if c in out.columns:
                    out[c] = out[c].astype(str).str.strip()
        else:
            for c in out.select_dtypes(include="object").columns:
                out[c] = out[c].str.strip()
        return out

    def _op_aggregate(self, df: pd.DataFrame, p: Dict[str, Any]) -> pd.DataFrame:
        """
        Agrège le DataFrame par groupes.

        Params:
            by: List[str] - colonnes de groupement
            agg: Dict - colonnes agrégées, format :
                {"out_col": {"func": "sum", "col": "src_col"}}
                Fonctions supportées : sum, count, mean, avg, min, max, first, last

        Exemple YAML:
            - aggregate:
                by: [category]
                agg:
                  total_revenue: {func: sum, col: revenue}
                  order_count: {func: count, col: order_id}
                  avg_price: {func: mean, col: unit_price}
        """
        by = p.get("by")
        if not by:
            raise ValueError("aggregate.by is required (a non-empty list of columns)")
        if isinstance(by, str):
            by = [by]
        if not all(c in df.columns for c in by):
            missing = [c for c in by if c not in df.columns]
            raise ValueError(
                f"aggregate.by: unknown columns {missing}. "
                f"Available columns: {list(df.columns)}"
            )

        agg_config = p.get("agg")
        if not agg_config or not isinstance(agg_config, dict):
            raise ValueError("aggregate.agg is required (a non-empty mapping)")

        # Mapping func aliases
        _FUNC_ALIASES = {"avg": "mean"}

        pandas_agg: Dict[str, tuple] = {}
        for out_col, spec in agg_config.items():
            if isinstance(spec, dict):
                func = str(spec.get("func", "sum")).lower()
                func = _FUNC_ALIASES.get(func, func)
                src_col = spec.get("col", out_col)
            elif isinstance(spec, str):
                func = spec.lower()
                func = _FUNC_ALIASES.get(func, func)
                src_col = out_col
            else:
                raise ValueError(
                    f"aggregate.agg.{out_col}: invalid format. "
                    f"Expected {{func, col}} or a function name."
                )
            if src_col not in df.columns:
                raise ValueError(
                    f"aggregate.agg.{out_col}: unknown source column '{src_col}'. "
                    f"Available columns: {list(df.columns)}"
                )
            # sum / mean sur du texte : pandas concatène les chaînes ("19.9" +
            # "49.9" -> "19.949.9") au lieu d'additionner. Une colonne lue d'un
            # CSV sans `cast` est du texte : on refuse plutôt que de produire
            # un total faux sans le dire.
            if func in ("sum", "mean"):
                col = df[src_col]
                if col.dtype.kind not in "iufb" and col.notna().any():
                    raise ValueError(
                        f"aggregate.agg.{out_col}: {func} needs a numeric column "
                        f"('{src_col}' is {col.dtype}). Add a cast step before aggregate, "
                        f"for example: cast: {{mapping: {{{src_col}: float}}}}"
                    )
            pandas_agg[out_col] = (src_col, func)

        try:
            result = df.groupby(by, as_index=False).agg(**pandas_agg)
            return result.reset_index(drop=True)
        except Exception as e:
            raise ValueError(f"aggregate: {e}") from None

    # --------------------------------------------------
    # Helpers
    # --------------------------------------------------

    @staticmethod
    def _decimal_strings_only(series: pd.Series) -> bool:
        """
        Vrai si la colonne est une colonne de texte dont **aucune** valeur ne
        contient autre chose que des caractères décimaux `[0-9 + - . e E]` ou des
        blancs.

        C'est la condition qui rend `astype` interchangeable avec `to_numeric` :
        `astype` reconnaît en plus l'hexadécimal (`"0x10"` → 16), les tirets bas
        (`"1_000"`), les mots `nan` / `inf`, et les chiffres non ASCII, que
        `to_numeric` refuse. Tous exigent un caractère hors de cet ensemble.

        La vérification est faite par pyarrow (une passe C++ sur le tampon de
        caractères) : sans pyarrow, ou sur une colonne d'objets, il n'existe pas
        de test assez rapide pour valoir la peine, et on répond non.
        """
        if series.empty or getattr(series.dtype, "storage", None) != "pyarrow":
            return False
        try:
            import pyarrow as pa
            import pyarrow.compute as pc

            arr = pa.array(series.array)
            if not (pa.types.is_string(arr.type) or pa.types.is_large_string(arr.type)):
                return False
            ok = pc.all(pc.match_substring_regex(arr, r"^[0-9+\-.eE \t\r\n]*$"),
                        min_count=0).as_py()
            return ok is True
        except Exception:  # noqa: BLE001 - pyarrow absent ou type inattendu
            return False

    @staticmethod
    def _to_numeric_fast(series: pd.Series, dtype: str) -> pd.Series:
        """
        Conversion numérique d'une colonne, résultat identique à
        ``pd.to_numeric(series, errors="raise").astype(dtype)``.

        `astype` lit les chaînes de caractères directement (une passe C), là où
        `to_numeric` construit un tableau d'objets Python : cinq à dix fois plus
        rapide sur un million de lignes. Mais les deux ne reconnaissent pas la
        même grammaire, donc le chemin rapide n'est pris que sur une colonne
        vérifiée décimale (`_decimal_strings_only`) — et toute valeur qu'il
        refuse malgré tout repasse par `to_numeric`, qui reste la référence :
        même résultat, même message d'erreur.
        """
        if PandasEngine._decimal_strings_only(series):
            try:
                out = series.astype(dtype)
            except (ValueError, TypeError):
                out = None
            if out is not None and not PandasEngine._has_negative_zero(out):
                return out
        return pd.to_numeric(series, errors="raise").astype(dtype)

    @staticmethod
    def _has_negative_zero(series: pd.Series) -> bool:
        """
        Dernier écart connu entre les deux voies : `to_numeric` lit `"-0"` comme
        l'entier 0 et rend `+0.0`, tandis qu'`astype` rend `-0.0` (`"-0.0"`, lui,
        donne `-0.0` des deux côtés). Le cas est rare ; on le détecte d'une passe
        vectorisée et on laisse alors la référence faire le travail.
        """
        if series.dtype != "float64":
            return False
        values = np.asarray(series, dtype="float64")
        return bool(np.any(np.signbit(values) & (values == 0.0)))

    def _cast_to_bool(self, series: pd.Series) -> pd.Series:
        """
        Convertit une Series vers boolean avec gestion flexible des formats.
        """
        TRUE_VALS  = {"true", "1", "yes", "oui", "on"}
        FALSE_VALS = {"false", "0", "no", "non", "off"}

        def normalize(v):
            if isinstance(v, bool):
                return v
            if isinstance(v, (int, float)):
                if v == 1:
                    return True
                if v == 0:
                    return False
                raise ValueError(f"Numeric value {v} cannot be converted to bool (expected 0 or 1)")
            if isinstance(v, str):
                s = v.strip().lower()
                if s in TRUE_VALS:
                    return True
                if s in FALSE_VALS:
                    return False
                raise ValueError(f"String '{v}' cannot be converted to bool")
            raise ValueError(f"Type {type(v).__name__} cannot be converted to bool")

        # `normalize` est une fonction Python : l'appeler une fois par ligne coûte
        # cher. Une colonne booléenne n'a en pratique qu'une poignée de valeurs
        # distinctes, donc on ne l'appelle qu'une fois par valeur distincte puis
        # on substitue. `unique()` conserve l'ordre d'apparition : la première
        # valeur invalide, et donc le message d'erreur, restent les mêmes.
        if series.empty:
            return series.map(normalize)
        try:
            uniques = pd.unique(series)
            # `map` passe des objets Python à la fonction ; `unique` rend des
            # scalaires numpy (np.bool_, np.int64), que `normalize` refuserait.
            # `tolist()` rétablit les types que voyait l'implémentation d'origine.
            table = {v: normalize(v) for v in uniques.tolist()}
        except TypeError:
            # Valeurs non hachables (listes, dicts) : `unique` ne sait pas les
            # traiter, on revient au parcours ligne à ligne.
            return series.map(normalize)
        return series.map(table)
