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
from typing import Any, Dict, List

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
    ) -> StepResult:
        """
        Applique une transformation unique sur un DataFrame Pandas.

        Args:
            dataset: DataFrame Pandas à transformer
            step: Définition de l'étape (format normalisé ou DSL)
                  Ex: {"op": "select", "params": {"columns": [...]}}
                  Ex: {"select": {"columns": [...]}}

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
    ) -> Any:
        """
        Applique une séquence de transformations sur un DataFrame.

        Args:
            dataset: DataFrame Pandas initial
            steps: Liste d'étapes de transformation

        Returns:
            DataFrame transformé après toutes les étapes

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
        for idx, step in enumerate(steps, start=1):
            try:
                df = self.apply_step(df, step).output
            except ValueError as e:
                raise ValueError(f"Erreur à l'étape {idx}/{len(steps)}: {e}") from None

        return df

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

        raise ValueError(
            f"Opération non supportée (MVP) : '{step.op}'. "
            f"Opérations disponibles : select, rename, cast, filter, calculate"
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

    # --------------------------------------------------
    # Helpers
    # --------------------------------------------------

    def _cast_to_bool(self, series: pd.Series) -> pd.Series:
        """
        Convertit une Series vers boolean avec gestion flexible des formats.

        Supporte :
        - bool natif : True, False
        - int : 1 (True), 0 (False)
        - float : 1.0 (True), 0.0 (False)
        - string : "true", "1" (True), "false", "0" (False) - insensible à la casse
        """

        def normalize(v):
            # Si déjà bool
            if isinstance(v, bool):
                return v

            # Si numérique 0 ou 1
            if isinstance(v, (int, float)):
                if v == 1:
                    return True
                if v == 0:
                    return False
                raise ValueError(f"Valeur numérique invalide pour bool : {v}")

            # Si string
            if isinstance(v, str):
                v = v.strip().lower()
                if v in {"true", "1", "yes", "y"}:
                    return True
                if v in {"false", "0", "no", "n"}:
                    return False

            raise ValueError(f"Impossible de convertir en bool : {v!r}")

        return series.map(normalize).astype("boolean")