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
    key: Any
    how: str = "inner"

    @field_validator("how")
    @classmethod
    def _valid_how(cls, v: str) -> str:
        allowed = {"inner", "left", "right", "outer"}
        if v not in allowed:
            raise ValueError(f"join.how invalide: {v} (attendu: {sorted(allowed)})")
        return v

    @field_validator("key")
    @classmethod
    def _valid_key(cls, v: Any) -> Any:
        if isinstance(v, str):
            if not v.strip():
                raise ValueError("join.key ne peut pas etre vide")
            return v
        if isinstance(v, list) and v and all(isinstance(x, str) and x.strip() for x in v):
            return v
        raise ValueError("join.key doit etre une colonne (str) ou une liste de colonnes non vides")

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


# -----------------------------
# Registre des operations
# -----------------------------

OpName = Literal[
    "select", "rename", "cast", "filter", "calculate",
    "sort", "deduplicate", "fill_null", "trim", "aggregate", "join",
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
        for key in ("columns", "by", "subset"):
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
