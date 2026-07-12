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

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pandas as pd

from internal.transform.engine_interface import StepResult, TransformEngine


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
                f"PandasEngine attend un pandas.DataFrame, reçu {type(dataset).__name__}"
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
            raise ValueError("Pipeline vide : au moins une transformation requise")

        if not isinstance(steps, list):
            raise ValueError(
                f"steps doit être une liste, reçu {type(steps).__name__}"
            )

        df = dataset
        all_stats: list = []
        for idx, step in enumerate(steps, start=1):
            try:
                result = self.apply_step(df, step, context=context)
                df = result.output
                all_stats.append({"index": idx, "stats": result.stats})
            except ValueError as e:
                raise ValueError(f"Erreur à l'étape {idx}/{len(steps)}: {e}") from None

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
            raise ValueError(f"Step doit être un dict, reçu {type(step).__name__}")

        # Format normalisé : {"op": ..., "params": ...}
        if "op" in step:
            op = step["op"]
            if not isinstance(op, str):
                raise ValueError(f"op doit être un string, reçu {type(op).__name__}")

            return _NormalizedStep(
                op=op.lower(),
                params=step.get("params", {}),
            )

        # Format DSL : {"select": {...}}
        if len(step) != 1:
            raise ValueError(
                f"Step invalide : doit contenir 1 clé (opération), trouvé {len(step)}"
            )

        op = next(iter(step))
        params = step[op]

        if not isinstance(params, dict):
            raise ValueError(
                f"Paramètres de '{op}' doivent être un dict, reçu {type(params).__name__}"
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

        raise ValueError(
            f"Opération inconnue: {step.op}. "
            f"Opérations disponibles : select, rename, cast, filter, calculate, sort, deduplicate, fill_null, trim, aggregate, join"
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
            raise ValueError("select.columns requis et ne peut pas être vide")

        if not isinstance(cols, list):
            raise ValueError(
                f"select.columns doit être une liste, reçu {type(cols).__name__}"
            )

        if not all(isinstance(c, str) for c in cols):
            raise ValueError("select.columns doit contenir uniquement des strings")

        # Déduplication tout en préservant l'ordre
        cols = list(dict.fromkeys(cols))

        missing = [c for c in cols if c not in df.columns]
        if missing:
            raise ValueError(
                f"select : colonnes inexistantes {missing}. "
                f"Colonnes disponibles : {list(df.columns)}"
            )

        return df.loc[:, cols].copy()

    def _op_rename(self, df: pd.DataFrame, p: Dict[str, Any]) -> pd.DataFrame:
        """
        Renomme des colonnes.

        Params:
            mapping: Dict[str, str] - {"old_name": "new_name"}
        """
        mapping = p.get("mapping")

        if not mapping:
            raise ValueError("rename.mapping requis et ne peut pas être vide")

        if not isinstance(mapping, dict):
            raise ValueError(
                f"rename.mapping doit être un dict, reçu {type(mapping).__name__}"
            )

        missing = [c for c in mapping.keys() if c not in df.columns]
        if missing:
            raise ValueError(
                f"rename : colonnes inexistantes {missing}. "
                f"Colonnes disponibles : {list(df.columns)}"
            )

        return df.rename(columns=mapping).copy()

    def _op_cast(self, df: pd.DataFrame, p: Dict[str, Any]) -> pd.DataFrame:
        """
        Convertit le type de colonnes.

        Params:
            mapping: Dict[str, str] - {"column": "type"}
            Types supportés: int, integer, float, str, string, bool, boolean, datetime
        """
        mapping = p.get("mapping")

        if not mapping:
            raise ValueError("cast.mapping requis et ne peut pas être vide")

        if not isinstance(mapping, dict):
            raise ValueError(
                f"cast.mapping doit être un dict, reçu {type(mapping).__name__}"
            )

        out = df.copy()

        for col, typ in mapping.items():
            if col not in out.columns:
                raise ValueError(
                    f"cast : colonne inexistante '{col}'. "
                    f"Colonnes disponibles : {list(out.columns)}"
                )

            if not isinstance(typ, str):
                raise ValueError(
                    f"cast : type pour '{col}' doit être un string, reçu {type(typ).__name__}"
                )

            t = typ.lower()

            try:
                if t in {"int", "integer"}:
                    out[col] = pd.to_numeric(out[col], errors="raise").astype("Int64")

                elif t == "float":
                    out[col] = pd.to_numeric(out[col], errors="raise").astype(
                        "float64"
                    )

                elif t in {"str", "string"}:
                    out[col] = out[col].astype("string")

                elif t in {"bool", "boolean"}:
                    out[col] = self._cast_to_bool(out[col])

                elif t.startswith("datetime"):
                    out[col] = pd.to_datetime(out[col], errors="raise")

                else:
                    raise ValueError(
                        f"Type non supporté : '{typ}'. "
                        f"Types disponibles : int, float, str, bool, datetime"
                    )

            except ValueError as e:
                # Re-raise ValueError avec contexte ajouté
                if "Type non supporté" in str(e):
                    raise
                raise ValueError(
                    f"cast : échec conversion colonne='{col}' vers type='{typ}' : {e}"
                ) from None
            except Exception as e:
                raise ValueError(
                    f"cast : échec conversion colonne='{col}' vers type='{typ}' : {e}"
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
            raise ValueError("filter.expr requis et ne peut pas être vide")

        if not isinstance(expr, str):
            raise ValueError(
                f"filter.expr doit être un string, reçu {type(expr).__name__}"
            )

        expr = expr.strip()
        if not expr:
            raise ValueError("filter.expr ne peut pas être un string vide")

        try:
            return df.query(expr, engine="python").copy()
        except Exception as e:
            raise ValueError(
                f"filter : expression invalide '{expr}'. Erreur : {e}"
            ) from None

    def _op_join(self, df: pd.DataFrame, p: Dict[str, Any]) -> pd.DataFrame:
        """
        Jointure avec une source de reference.

        Le runner precharge les lignes de la source droite dans p["_right_rows"].
        Params: on (str|list), how (inner|left|right|outer).
        """
        right_rows = p.get("_right_rows")
        if right_rows is None:
            raise ValueError(
                "join: source de reference non chargee. "
                "Le step 'join' doit etre execute via le runner (source 'right' requise)."
            )
        how = p.get("how", "inner")
        if how not in ("inner", "left", "right", "outer"):
            raise ValueError(f"join.how invalide: {how} (inner|left|right|outer)")
        right_df = pd.DataFrame(list(right_rows))

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
            raise ValueError("join: 'key' (ou 'left_key' + 'right_key') requis")
        keys = [key] if isinstance(key, str) else list(key)
        for k in keys:
            if k not in df.columns:
                raise ValueError(f"join: cle '{k}' absente du flux gauche")
            if k not in right_df.columns:
                raise ValueError(f"join: cle '{k}' absente de la source de reference")
        return df.merge(right_df, on=keys, how=how, suffixes=("", "_r"))

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
            raise ValueError("calculate.column requis et ne peut pas être vide")

        if not expr:
            raise ValueError("calculate.expr requis et ne peut pas être vide")

        if not isinstance(col, str):
            raise ValueError(
                f"calculate.column doit être un string, reçu {type(col).__name__}"
            )

        if not isinstance(expr, str):
            raise ValueError(
                f"calculate.expr doit être un string, reçu {type(expr).__name__}"
            )

        col = col.strip()
        expr = expr.strip()

        if not col:
            raise ValueError("calculate.column ne peut pas être un string vide")

        if not expr:
            raise ValueError("calculate.expr ne peut pas être un string vide")

        out = df.copy()
        try:
            out[col] = out.eval(expr, engine="python")
        except Exception as e:
            raise ValueError(
                f"calculate : expression invalide '{expr}'. Erreur : {e}"
            ) from None

        return out

    def _op_sort(self, df: pd.DataFrame, p: Dict[str, Any]) -> pd.DataFrame:
        """
        Trie le DataFrame.

        Params:
            by: List[str] - colonnes de tri
            ascending: bool | List[bool] - ordre (defaut True)
        """
        by = p.get("by")
        if not by:
            raise ValueError("sort.by requis (liste de colonnes)")
        if isinstance(by, str):
            by = [by]
        ascending = p.get("ascending", True)
        return df.sort_values(by=by, ascending=ascending).reset_index(drop=True)

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

    def _op_trim(self, df: pd.DataFrame, p: Dict[str, Any]) -> pd.DataFrame:
        """
        Supprime les espaces superflus sur les colonnes string.

        Params:
            columns: List[str] - colonnes a trimmer (defaut : toutes les colonnes string)
        """
        cols = p.get("columns")
        out = df.copy()
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
            raise ValueError("aggregate.by requis (liste de colonnes non vide)")
        if isinstance(by, str):
            by = [by]
        if not all(c in df.columns for c in by):
            missing = [c for c in by if c not in df.columns]
            raise ValueError(
                f"aggregate.by : colonnes inexistantes {missing}. "
                f"Colonnes disponibles : {list(df.columns)}"
            )

        agg_config = p.get("agg")
        if not agg_config or not isinstance(agg_config, dict):
            raise ValueError("aggregate.agg requis (dict non vide)")

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
                    f"aggregate.agg.{out_col}: format invalide. "
                    f"Attendu: dict {{func, col}} ou string func."
                )
            if src_col not in df.columns:
                raise ValueError(
                    f"aggregate.agg.{out_col}: colonne source '{src_col}' inexistante. "
                    f"Colonnes disponibles : {list(df.columns)}"
                )
            pandas_agg[out_col] = (src_col, func)

        try:
            result = df.groupby(by, as_index=False).agg(**pandas_agg)
            return result.reset_index(drop=True)
        except Exception as e:
            raise ValueError(f"aggregate: erreur lors de l'agregation: {e}") from None

    # --------------------------------------------------
    # Helpers
    # --------------------------------------------------

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
                raise ValueError(f"Valeur numerique {v} non convertible en bool (attendu 0 ou 1)")
            if isinstance(v, str):
                s = v.strip().lower()
                if s in TRUE_VALS:
                    return True
                if s in FALSE_VALS:
                    return False
                raise ValueError(f"String '{v}' non convertible en bool")
            raise ValueError(f"Type {type(v).__name__} non convertible en bool")

        return series.map(normalize)
