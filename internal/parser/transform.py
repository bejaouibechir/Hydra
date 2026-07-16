"""
Parser + validation Pydantic pour transformations.yaml (Hydra DSL v1.1).
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Type

from pydantic import BaseModel, Field, field_validator, model_validator


# -----------------------------
# Modeles des operations
# -----------------------------

class SelectOp(BaseModel):
    columns: List[str] = Field(min_length=1)

    @field_validator("columns")
    @classmethod
    def _non_empty_columns(cls, v: List[str]) -> List[str]:
        cleaned = [c.strip() for c in v if isinstance(c, str)]
        if not cleaned or any(not c for c in cleaned):
            raise ValueError("select.columns doit contenir des noms de colonnes non vides")
        seen = set()
        uniq: List[str] = []
        for c in cleaned:
            if c not in seen:
                uniq.append(c)
                seen.add(c)
        return uniq


class RenameOp(BaseModel):
    mapping: Dict[str, str] = Field(min_length=1)

    @field_validator("mapping")
    @classmethod
    def _valid_mapping(cls, v: Dict[str, str]) -> Dict[str, str]:
        cleaned: Dict[str, str] = {}
        for old, new in v.items():
            if not isinstance(old, str) or not isinstance(new, str):
                raise ValueError("rename.mapping doit etre un dict str->str")
            old2, new2 = old.strip(), new.strip()
            if not old2 or not new2:
                raise ValueError("rename.mapping ne peut pas contenir de cles/valeurs vides")
            cleaned[old2] = new2
        return cleaned


class CastOp(BaseModel):
    mapping: Dict[str, str] = Field(min_length=1)

    @field_validator("mapping")
    @classmethod
    def _valid_casts(cls, v: Dict[str, str]) -> Dict[str, str]:
        allowed = {"int", "float", "str", "bool", "date", "datetime"}
        cleaned: Dict[str, str] = {}
        for col, typ in v.items():
            if not isinstance(col, str) or not isinstance(typ, str):
                raise ValueError("cast.mapping doit etre un dict str->str")
            col2, typ2 = col.strip(), typ.strip().lower()
            if not col2 or not typ2:
                raise ValueError("cast.mapping ne peut pas contenir de cles/valeurs vides")
            if typ2 not in allowed:
                raise ValueError(
                    f"type de cast invalide: {typ2} (attendu: {sorted(allowed)})"
                )
            cleaned[col2] = typ2
        return cleaned


class FilterOp(BaseModel):
    expr: str = Field(min_length=1)

    @field_validator("expr")
    @classmethod
    def _strip_expr(cls, v: str) -> str:
        v2 = v.strip()
        if not v2:
            raise ValueError("filter.expr ne peut pas etre vide")
        return v2


class CalculateOp(BaseModel):
    column: str = Field(min_length=1)
    expr: str = Field(min_length=1)

    @field_validator("column")
    @classmethod
    def _strip_col(cls, v: str) -> str:
        v2 = v.strip()
        if not v2:
            raise ValueError("calculate.column ne peut pas etre vide")
        return v2

    @field_validator("expr")
    @classmethod
    def _strip_expr(cls, v: str) -> str:
        v2 = v.strip()
        if not v2:
            raise ValueError("calculate.expr ne peut pas etre vide")
        return v2


class SortOp(BaseModel):
    by: List[str] = Field(min_length=1)
    ascending: Any = True


class DeduplicateOp(BaseModel):
    columns: Optional[List[str]] = None
    keep: str = "first"


class FillNullOp(BaseModel):
    value: Optional[Any] = None
    columns: Optional[Dict[str, Any]] = None


class TrimOp(BaseModel):
    columns: Optional[List[str]] = None


class AggregateOp(BaseModel):
    """
    Agrégation groupée.

    Params YAML:
        by: [col1, col2]          # colonnes de groupement
        agg:
          out_col: {func: sum, col: src_col}
          out_col2: {func: count, col: src_col2}
          out_col3: {func: mean, col: src_col3}

    Fonctions supportées: sum, count, mean, avg, min, max, first, last
    """
    by: List[str] = Field(min_length=1)
    agg: Dict[str, Any] = Field(min_length=1)


class JoinOp(BaseModel):
    """
    Jointure avec une source de reference (2e flux).

    Params YAML:
        join:
          right:                    # source de reference (comme une source)
            type: mysql
            connection: {...}
            extract: {table: departments}
          key: email                # cle commune (str ou liste de str)
          how: left                 # inner | left | right | outer
    """
    right: Any
    key: Any = None
    left_key: Any = None
    right_key: Any = None
    how: str = "inner"

    @field_validator("how")
    @classmethod
    def _valid_how(cls, v: str) -> str:
        allowed = {"inner", "left", "right", "outer"}
        if v not in allowed:
            raise ValueError(f"join.how invalide: {v} (attendu: {sorted(allowed)})")
        return v

    @field_validator("key", "left_key", "right_key")
    @classmethod
    def _valid_key(cls, v: Any) -> Any:
        if v is None:
            return v
        if isinstance(v, str):
            if not v.strip():
                raise ValueError("join: cle vide")
            return v
        if isinstance(v, list) and v and all(isinstance(x, str) and x.strip() for x in v):
            return v
        raise ValueError("join: cle doit etre une colonne (str) ou une liste de colonnes non vides")

    @model_validator(mode="after")
    def _check_keys(self):
        has_single = self.key is not None
        has_pair = self.left_key is not None and self.right_key is not None
        if not has_single and not has_pair:
            raise ValueError("join: fournir 'key' (colonne commune) ou 'left_key' + 'right_key'")
        return self

    @field_validator("right")
    @classmethod
    def _valid_right(cls, v: Any) -> Any:
        # id de source declaree (str) OU source inline (dict avec 'type')
        if isinstance(v, str):
            if not v.strip():
                raise ValueError("join.right (id de source) ne peut pas etre vide")
            return v
        if isinstance(v, dict) and v.get("type"):
            return v
        raise ValueError("join.right doit etre un id de source (str) ou une source inline (dict avec 'type')")


class CleanOp(BaseModel):
    """Nettoie les colonnes texte : espaces (trim + multiples) + casse."""
    columns: Optional[List[str]] = None       # defaut: toutes les colonnes texte
    case: str = "none"                         # none | lower | upper

    @field_validator("case")
    @classmethod
    def _valid_case(cls, v: str) -> str:
        if v not in ("none", "lower", "upper"):
            raise ValueError("clean.case doit etre none|lower|upper")
        return v


class PivotOp(BaseModel):
    """Long -> large (pandas pivot_table)."""
    index: List[str] = Field(min_length=1)     # colonnes conservees en lignes
    column: str                                # colonne dont les valeurs deviennent des colonnes
    values: str                                # colonne des valeurs
    aggfunc: str = "first"                     # sum|mean|first|min|max|count...


class UnpivotOp(BaseModel):
    """Large -> long (pandas melt)."""
    id_vars: List[str] = Field(min_length=1)   # colonnes conservees
    value_vars: Optional[List[str]] = None     # colonnes a depivoter (defaut: le reste)
    var_name: str = "variable"
    value_name: str = "value"


class TransposeOp(BaseModel):
    """Transpose lignes <-> colonnes (pandas .T)."""
    index_col: Optional[str] = None   # colonne dont les valeurs deviennent les en-tetes
    header_name: str = "column"       # nom de la colonne recevant les anciens en-tetes


class MergeOp(BaseModel):
    """Merge type SQL Server (upsert cible <- source, sur une cle)."""
    right: Any                        # 2e source (id declare ou source inline)
    key: Any                          # cle d'appariement (str ou liste)
    delete_unmatched: bool = False    # supprime les lignes cible absentes de la source

    @field_validator("key")
    @classmethod
    def _valid_key(cls, v: Any) -> Any:
        if isinstance(v, str) and v.strip():
            return v
        if isinstance(v, list) and v and all(isinstance(x, str) and x.strip() for x in v):
            return v
        raise ValueError("merge.key doit etre une colonne (str) ou une liste non vide")

    @field_validator("right")
    @classmethod
    def _valid_right(cls, v: Any) -> Any:
        if isinstance(v, str) and v.strip():
            return v
        if isinstance(v, dict) and v.get("type"):
            return v
        raise ValueError("merge.right doit etre un id de source (str) ou une source inline (dict avec 'type')")


class UnionOp(BaseModel):
    """Union / Union All : empile une 2e source (memes colonnes)."""
    right: Any                        # 2e source (id declare ou source inline)
    distinct: bool = False            # True = UNION (dedoublonne) ; False = UNION ALL

    @field_validator("right")
    @classmethod
    def _valid_right(cls, v: Any) -> Any:
        if isinstance(v, str) and v.strip():
            return v
        if isinstance(v, dict) and v.get("type"):
            return v
        raise ValueError("union.right doit etre un id de source (str) ou une source inline (dict avec 'type')")


class ScriptOp(BaseModel):
    """
    Transformation Python personnalisee (facon SSIS Script Component).

    L'utilisateur declare un contrat colonnes input -> colonnes output et
    fournit un extrait de code Python execute dans un environnement restreint.

    Params YAML:
        script:
          inputs: [price, quantity]      # colonnes lues (contrat)
          outputs:                       # colonnes produites (+ type)
            total: float
            label: str
          mode: vectorized               # vectorized | row
          code: |
            total = price * quantity
            label = "big" if total.iloc[0] > 100 else "small"

    Modes:
    - vectorized : chaque colonne input est exposee comme pandas.Series ;
                   le code doit affecter chaque colonne output (Series/scalaire).
    - row        : le code s'execute ligne par ligne (facon SSIS
                   ProcessInputRow) ; chaque colonne input est un scalaire.

    Types outputs autorises: int, float, str, bool, date, datetime, any.
    """
    inputs: List[str] = Field(default_factory=list)
    outputs: Dict[str, str] = Field(min_length=1)
    code: str = Field(min_length=1)
    mode: Literal["vectorized", "row"] = "vectorized"

    @field_validator("inputs")
    @classmethod
    def _clean_inputs(cls, v: List[str]) -> List[str]:
        cleaned = [c.strip() for c in v if isinstance(c, str) and c.strip()]
        seen = set()
        uniq: List[str] = []
        for c in cleaned:
            if c not in seen:
                uniq.append(c)
                seen.add(c)
        return uniq

    @field_validator("outputs")
    @classmethod
    def _valid_outputs(cls, v: Dict[str, str]) -> Dict[str, str]:
        allowed = {"int", "float", "str", "bool", "date", "datetime", "any"}
        cleaned: Dict[str, str] = {}
        for col, typ in v.items():
            if not isinstance(col, str) or not isinstance(typ, str):
                raise ValueError("script.outputs doit etre un dict str->str")
            col2, typ2 = col.strip(), typ.strip().lower()
            if not col2:
                raise ValueError("script.outputs: nom de colonne vide")
            if typ2 not in allowed:
                raise ValueError(
                    f"script.outputs: type invalide '{typ2}' pour '{col2}' "
                    f"(attendu: {sorted(allowed)})"
                )
            cleaned[col2] = typ2
        if not cleaned:
            raise ValueError("script.outputs ne peut pas etre vide")
        return cleaned

    @field_validator("code")
    @classmethod
    def _strip_code(cls, v: str) -> str:
        v2 = v.strip("\n")
        if not v2.strip():
            raise ValueError("script.code ne peut pas etre vide")
        return v2


# -----------------------------
# Registre des operations
# -----------------------------

OpName = Literal[
    "select", "rename", "cast", "filter", "calculate",
    "sort", "deduplicate", "fill_null", "trim", "aggregate", "join",
    "clean", "pivot", "unpivot", "transpose", "merge", "union", "script",
]

_OP_MODEL_MAP: Dict[str, Type[BaseModel]] = {
    "select": SelectOp,
    "rename": RenameOp,
    "cast": CastOp,
    "filter": FilterOp,
    "calculate": CalculateOp,
    "sort": SortOp,
    "deduplicate": DeduplicateOp,
    "fill_null": FillNullOp,
    "trim": TrimOp,
    "aggregate": AggregateOp,
    "join": JoinOp,
    "clean": CleanOp,
    "pivot": PivotOp,
    "unpivot": UnpivotOp,
    "transpose": TransposeOp,
    "merge": MergeOp,
    "union": UnionOp,
    "script": ScriptOp,
}


# -----------------------------
# Step normalise
# -----------------------------

class TransformStep(BaseModel):
    op: OpName
    params: Any  # Dict apres validation, mais Any pour eviter le warning serialiseur Pydantic
    name: Optional[str] = None

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v2 = v.strip()
        return v2 if v2 else None

    @model_validator(mode="after")
    def _validate_params_by_op(self):
        model = _OP_MODEL_MAP[self.op]
        validated = model.model_validate(self.params)
        # Stocker le dict (pas l'objet Pydantic) pour eviter les warnings de serialisation
        self.params = validated.model_dump()
        return self


class TransformConfig(BaseModel):
    steps: List[TransformStep] = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def _normalize_root(cls, data: Any) -> Any:
        if isinstance(data, dict) and "steps" not in data and "transformations" in data:
            inner = data.get("transformations")
            if isinstance(inner, dict) and "steps" in inner:
                return {"steps": inner["steps"]}
        return data


class TransformParser:
    @staticmethod
    def _coerce_param_types(params: Any) -> Any:
        """Tolérance : coercition des params sérialisés en strings par
        d'anciennes versions de Studio — JSON string → dict, 'a,b' → liste,
        'false' → bool. Sans effet sur les params déjà bien typés."""
        import json
        if not isinstance(params, dict):
            return params
        out = dict(params)
        for key in ("mapping", "agg"):
            v = out.get(key)
            if isinstance(v, str) and v.strip().startswith("{"):
                try:
                    out[key] = json.loads(v)
                except Exception:
                    pass
        for key in ("columns", "by", "subset", "index", "id_vars", "value_vars", "inputs"):
            v = out.get(key)
            if isinstance(v, str):
                items = [s.strip() for s in v.split(",") if s.strip()]
                if items:
                    out[key] = items
                else:
                    out.pop(key, None)
        if isinstance(out.get("ascending"), str):
            out["ascending"] = out["ascending"].strip().lower() not in ("false", "0", "no")
        return out

    def parse(self, raw: Dict[str, Any]) -> TransformConfig:
        converted = self._convert_steps(raw)
        return TransformConfig.model_validate(converted)

    def _convert_steps(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        data = raw

        if "steps" not in data and "transformations" in data and isinstance(data["transformations"], dict):
            data = {"steps": data["transformations"].get("steps")}

        steps = data.get("steps")
        if not isinstance(steps, list):
            raise ValueError("steps doit etre une liste")

        converted_steps: List[Dict[str, Any]] = []

        for idx, step in enumerate(steps, start=1):
            if not isinstance(step, dict) or len(step) != 1:
                raise ValueError(
                    f"Step #{idx} invalide: chaque step doit etre un dict a 1 seule cle"
                )

            op = next(iter(step.keys()))
            params = step[op]

            if op not in _OP_MODEL_MAP:
                raise ValueError(f"Operation inconnue: {op}")

            if not isinstance(params, dict):
                raise ValueError(f"Step '{op}' invalide: les parametres doivent etre un dictionnaire")

            converted_steps.append({"op": op, "params": self._coerce_param_types(params)})

        return {"steps": converted_steps}
