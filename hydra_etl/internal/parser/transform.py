"""
Parser + validation Pydantic pour transformations.yaml (Hydra DSL v1.1).
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Type, Union

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
            raise ValueError("select.columns must contain non-empty column names")
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
                raise ValueError("rename.mapping must be a mapping str -> str")
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
                raise ValueError("cast.mapping must be a mapping str -> str")
            col2, typ2 = col.strip(), typ.strip().lower()
            if not col2 or not typ2:
                raise ValueError("cast.mapping ne peut pas contenir de cles/valeurs vides")
            if typ2 not in allowed:
                raise ValueError(
                    f"invalid cast type: {typ2} (expected: {sorted(allowed)})"
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
          how: left                 # inner | left | right | outer | cross

    how: cross: cartesian product (every row x every right row), no key;
    max_rows guard (default 10,000,000 rows produced).
    """
    right: Any
    key: Any = None
    left_key: Any = None
    right_key: Any = None
    how: str = "inner"
    max_rows: Optional[int] = Field(
        default=None, description="how: cross only. Maximum rows produced (default 10,000,000).")

    @field_validator("how")
    @classmethod
    def _valid_how(cls, v: str) -> str:
        allowed = {"inner", "left", "right", "outer", "cross"}
        if v not in allowed:
            raise ValueError(f"join.how invalid: {v} (expected: {sorted(allowed)})")
        return v

    @field_validator("key", "left_key", "right_key")
    @classmethod
    def _valid_key(cls, v: Any) -> Any:
        if v is None:
            return v
        if isinstance(v, str):
            if not v.strip():
                raise ValueError("join: empty key")
            return v
        if isinstance(v, list) and v and all(isinstance(x, str) and x.strip() for x in v):
            return v
        raise ValueError("join: the key must be a column (str) or a non-empty list of columns")

    @field_validator("max_rows")
    @classmethod
    def _valid_max_rows(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and (isinstance(v, bool) or v < 1):
            raise ValueError("join.max_rows must be a positive integer")
        return v

    @model_validator(mode="after")
    def _check_keys(self):
        if self.how == "cross":
            given = [k for k in ("key", "left_key", "right_key") if getattr(self, k) is not None]
            if given:
                raise ValueError(f"join: how: cross takes no key — remove {', '.join(given)}")
            return self
        if self.max_rows is not None:
            raise ValueError("join.max_rows only applies to how: cross")
        has_single = self.key is not None
        has_pair = self.left_key is not None and self.right_key is not None
        if not has_single and not has_pair:
            raise ValueError("join: give 'key' (a common column) or 'left_key' + 'right_key'")
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
        raise ValueError("join.right must be a source id (str) or an inline source (a mapping with 'type')")


class CleanOp(BaseModel):
    """Nettoie les colonnes texte : espaces (trim + multiples) + casse."""
    columns: Optional[List[str]] = None       # defaut: toutes les colonnes texte
    case: str = "none"                         # none | lower | upper

    @field_validator("case")
    @classmethod
    def _valid_case(cls, v: str) -> str:
        if v not in ("none", "lower", "upper"):
            raise ValueError("clean.case must be none, lower or upper")
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
        raise ValueError("merge.key must be a column (str) or a non-empty list")

    @field_validator("right")
    @classmethod
    def _valid_right(cls, v: Any) -> Any:
        if isinstance(v, str) and v.strip():
            return v
        if isinstance(v, dict) and v.get("type"):
            return v
        raise ValueError("merge.right must be a source id (str) or an inline source (a mapping with 'type')")


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
        raise ValueError("union.right must be a source id (str) or an inline source (a mapping with 'type')")


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
                raise ValueError("script.outputs must be a mapping str -> str")
            col2, typ2 = col.strip(), typ.strip().lower()
            if not col2:
                raise ValueError("script.outputs: empty column name")
            if typ2 not in allowed:
                raise ValueError(
                    f"script.outputs: invalid type '{typ2}' for '{col2}' "
                    f"(expected: {sorted(allowed)})"
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


class TextToRowsOp(BaseModel):
    """
    One row per value of a text column ("a;b;c" -> 3 rows, other columns copied).
    A null value, or one with no non-empty part, keeps one row with a null value.

        text_to_rows:
          column: tags          # column to split (required)
          sep: ";"              # separator (default ","), plain text
          regex: false          # true: sep is a regular expression
          trim: true            # strip spaces around each value
          keep_empty: false     # empty values are dropped
          index_column: tag_pos # optional: position 1, 2, 3...
    """
    model_config = {"extra": "forbid"}

    column: str
    sep: str = ","
    regex: bool = False
    trim: bool = True
    keep_empty: bool = False
    index_column: Optional[str] = None

    @field_validator("column", "index_column")
    @classmethod
    def _non_empty_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not v.strip():
            raise ValueError("text_to_rows: column names cannot be empty")
        return v.strip()

    @field_validator("sep")
    @classmethod
    def _non_empty_sep(cls, v: str) -> str:
        if v == "":
            raise ValueError("text_to_rows.sep cannot be empty")
        return v

    @model_validator(mode="after")
    def _check(self):
        if self.regex:
            import re
            try:
                re.compile(self.sep)
            except re.error as e:
                raise ValueError(f"text_to_rows.sep is not a valid regular expression: {e}") from None
        if self.index_column is not None and self.index_column == self.column:
            raise ValueError("text_to_rows.index_column must differ from column")
        return self


class WindowOrderItem(BaseModel):
    """Item of window.order_by written as {col, desc}."""
    model_config = {"extra": "forbid"}
    col: str = Field(min_length=1, description="Column.")
    desc: bool = Field(default=False, description="true: descending (null values stay last).")


class WindowColumn(BaseModel):
    """A column added by window: its function and options."""
    model_config = {"extra": "forbid"}
    func: Literal[
        "row_number", "rank", "dense_rank", "lag", "lead",
        "cumsum", "cumcount", "cummin", "cummax",
        "sum", "mean", "min", "max", "count", "first", "last",
    ] = Field(description="Window function.")
    col: Optional[str] = Field(default=None, description="Column read by the function (not for row_number, rank, dense_rank).")
    offset: Optional[int] = Field(default=None, ge=1, description="lag / lead: rows to look back or ahead (default 1).")
    default: Optional[Any] = Field(default=None, description="lag / lead: value when the offset leaves the partition (default null).")


class WindowOp(BaseModel):
    """
    Window functions: adds columns and keeps every row, in its input order.
    Rank (row_number, rank, dense_rank), offset (lag, lead), running (cumsum,
    cumcount, cummin, cummax) and whole-partition (sum, mean, min, max, count,
    first, last) functions. Rank, offset and running functions need order_by.
    Full rules: internal/engines/window.py.
    """
    model_config = {"extra": "forbid"}

    partition_by: Optional[Union[str, List[str]]] = Field(
        default=None, description="Columns splitting the rows into independent partitions (whole table without it).")
    order_by: Optional[Union[str, List[Union[str, WindowOrderItem]]]] = Field(
        default=None, description="Order inside each partition: names or {col, desc}; nulls last, ties in input order.")
    columns: Dict[str, WindowColumn] = Field(
        min_length=1, description="Mapping of output_column: {func, col, offset, default}.")

    @model_validator(mode="before")
    @classmethod
    def _check(cls, data: Any) -> Any:
        from hydra_etl.internal.engines.window import check
        check(data)
        return data


# -----------------------------
# Registre des operations
# -----------------------------

OpName = Literal[
    "select", "rename", "cast", "filter", "calculate",
    "sort", "deduplicate", "fill_null", "trim", "aggregate", "join",
    "clean", "pivot", "unpivot", "transpose", "merge", "union", "script",
    "text_to_rows", "window",
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
    "text_to_rows": TextToRowsOp,
    "window": WindowOp,
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


ENGINES = ("auto", "pandas", "duckdb")


def _engine_of(data: Dict[str, Any]) -> Any:
    """`engine:` à la racine ou sous `transformations:` (forme écrite par Studio)."""
    if "engine" in data:
        return data["engine"]
    inner = data.get("transformations")
    if isinstance(inner, dict) and "engine" in inner:
        return inner["engine"]
    return None


class TransformConfig(BaseModel):
    steps: List[TransformStep] = Field(min_length=1)
    engine: Literal["auto", "pandas", "duckdb"] = Field(
        default="auto",
        description=(
            "Moteur des opérations globales (aggregate, sort). auto : pandas, sauf "
            "au-delà de HYDRA_LARGE_VOLUME_ROWS lignes estimées (2 000 000) où le moteur "
            "gros volumes (pyarrow + DuckDB, extra hydra-etl[duckdb]) est utilisé. "
            "pandas / duckdb : forcé. La variable HYDRA_ENGINE est prioritaire."
        ),
    )

    @field_validator("engine", mode="before")
    @classmethod
    def _lower_engine(cls, v: Any) -> Any:
        return v.strip().lower() if isinstance(v, str) else v

    @model_validator(mode="before")
    @classmethod
    def _normalize_root(cls, data: Any) -> Any:
        if isinstance(data, dict) and "steps" not in data and "transformations" in data:
            inner = data.get("transformations")
            if isinstance(inner, dict) and "steps" in inner:
                out = {"steps": inner["steps"]}
                engine = _engine_of(data)
                if engine is not None:
                    out["engine"] = engine
                return out
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
        engine = _engine_of(raw) if isinstance(raw, dict) else None

        if "steps" not in data and "transformations" in data and isinstance(data["transformations"], dict):
            data = {"steps": data["transformations"].get("steps")}

        steps = data.get("steps")
        if not isinstance(steps, list):
            raise ValueError("steps must be a list")

        converted_steps: List[Dict[str, Any]] = []

        for idx, step in enumerate(steps, start=1):
            if not isinstance(step, dict) or len(step) != 1:
                raise ValueError(
                    f"Step #{idx} is invalid: each step must be a mapping with exactly 1 key"
                )

            op = next(iter(step.keys()))
            params = step[op]

            if op not in _OP_MODEL_MAP:
                raise ValueError(f"Unknown operation: {op}")

            if not isinstance(params, dict):
                raise ValueError(f"Step '{op}' is invalid: its parameters must be a mapping")

            converted_steps.append({"op": op, "params": self._coerce_param_types(params)})

        out: Dict[str, Any] = {"steps": converted_steps}
        if engine is not None:
            out["engine"] = engine
        return out
