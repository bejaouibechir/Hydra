"""
Parser + validation Pydantic pour transformations.yaml (Hydra DSL v1.1 - MVP).

Objectif :
- Valider la structure des transformations (liste ordonnée de steps).
- Valider strictement un sous-ensemble d'opérations (MVP) :
  - select     : choisir un sous-ensemble de colonnes
  - rename     : renommer des colonnes
  - cast       : caster des colonnes vers un type cible
  - filter     : filtrer via une expression (string)
  - calculate  : créer/mettre à jour une colonne via une expression (string)

Important :
- Ce module NE fait PAS l'exécution : il valide et normalise.
- Les engines (pandas/duckdb) consommeront ensuite ces steps validés.

Convention DSL (entrée) :
Chaque step est un dict avec UNE SEULE clé opérationnelle, ex :
  - {"select": {"columns": ["id", "name"]}}
  - {"rename": {"mapping": {"old": "new"}}}
  - {"cast": {"mapping": {"price": "float"}}}
  - {"filter": {"expr": "id > 1"}}
  - {"calculate": {"column": "total", "expr": "price * qty"}}

Sortie normalisée :
TransformConfig(steps=[TransformStep(op=..., params=<model validé>, name=None), ...])
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Type

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator


# -----------------------------
# Modèles des opérations MVP
# -----------------------------

class SelectOp(BaseModel):
    """
    select: garder uniquement ces colonnes.
    """
    columns: List[str] = Field(min_length=1)

    @field_validator("columns")
    @classmethod
    def _non_empty_columns(cls, v: List[str]) -> List[str]:
        cleaned = [c.strip() for c in v if isinstance(c, str)]
        if not cleaned or any(not c for c in cleaned):
            raise ValueError("select.columns doit contenir des noms de colonnes non vides")

        # Déduplication en conservant l'ordre (évite doublons accidentels)
        seen = set()
        uniq: List[str] = []
        for c in cleaned:
            if c not in seen:
                uniq.append(c)
                seen.add(c)
        return uniq


class RenameOp(BaseModel):
    """
    rename: mapping {ancien: nouveau}.
    """
    mapping: Dict[str, str] = Field(min_length=1)

    @field_validator("mapping")
    @classmethod
    def _valid_mapping(cls, v: Dict[str, str]) -> Dict[str, str]:
        cleaned: Dict[str, str] = {}
        for old, new in v.items():
            if not isinstance(old, str) or not isinstance(new, str):
                raise ValueError("rename.mapping doit être un dict str->str")
            old2, new2 = old.strip(), new.strip()
            if not old2 or not new2:
                raise ValueError("rename.mapping ne peut pas contenir de clés/valeurs vides")
            cleaned[old2] = new2
        return cleaned


class CastOp(BaseModel):
    """
    cast: mapping {colonne: type}.
    Types supportés (MVP) :
      int, float, str, bool, date, datetime
    """
    mapping: Dict[str, str] = Field(min_length=1)

    @field_validator("mapping")
    @classmethod
    def _valid_casts(cls, v: Dict[str, str]) -> Dict[str, str]:
        # Alias normalisés vers les types canoniques (integer→int, string→str, boolean→bool)
        _ALIASES: Dict[str, str] = {"integer": "int", "string": "str", "boolean": "bool"}
        allowed = {"int", "float", "str", "bool", "date", "datetime"}
        cleaned: Dict[str, str] = {}

        for col, typ in v.items():
            if not isinstance(col, str) or not isinstance(typ, str):
                raise ValueError("cast.mapping doit être un dict str->str")

            col2, typ2 = col.strip(), typ.strip().lower()
            if not col2 or not typ2:
                raise ValueError("cast.mapping ne peut pas contenir de clés/valeurs vides")

            # Résoudre alias avant validation
            typ2 = _ALIASES.get(typ2, typ2)

            if typ2 not in allowed:
                raise ValueError(
                    f"type de cast invalide: '{typ}' "
                    f"(attendu: {sorted(allowed | set(_ALIASES.keys()))})"
                )

            cleaned[col2] = typ2

        return cleaned


class FilterOp(BaseModel):
    """
    filter: filtrer via une expression string.
    L'expression sera interprétée plus tard par l'engine.
    """
    expr: str = Field(min_length=1)

    @field_validator("expr")
    @classmethod
    def _strip_expr(cls, v: str) -> str:
        v2 = v.strip()
        if not v2:
            raise ValueError("filter.expr ne peut pas être vide")
        return v2


class CalculateOp(BaseModel):
    """
    calculate: créer/mettre à jour une colonne via une expression string.
    """
    column: str = Field(min_length=1)
    expr: str = Field(min_length=1)

    @field_validator("column")
    @classmethod
    def _strip_col(cls, v: str) -> str:
        v2 = v.strip()
        if not v2:
            raise ValueError("calculate.column ne peut pas être vide")
        return v2

    @field_validator("expr")
    @classmethod
    def _strip_expr(cls, v: str) -> str:
        v2 = v.strip()
        if not v2:
            raise ValueError("calculate.expr ne peut pas être vide")
        return v2


# -----------------------------
# Step normalisé (op -> params validés)
# -----------------------------

OpName = Literal["select", "rename", "cast", "filter", "calculate"]

_OP_MODEL_MAP: Dict[str, Type[BaseModel]] = {
    "select": SelectOp,
    "rename": RenameOp,
    "cast": CastOp,
    "filter": FilterOp,
    "calculate": CalculateOp,
}


class TransformStep(BaseModel):
    """
    Step normalisé :
    - op : nom de l'op
    - params : dict brut à l'entrée, remplacé par le modèle validé après validation
    - name : optionnel (support futur si on veut nommer les étapes)
    """
    op: OpName
    params: Dict[str, Any]
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
        """
        Validation cruciale :
        - On force le lien op -> modèle.
        - Sans ça, un Union naïf peut valider un payload incorrect
          en le faisant "matcher" un autre modèle.
        """
        model = _OP_MODEL_MAP[self.op]
        validated = model.model_validate(self.params)

        # On remplace les params dict par l'objet validé (utile pour la suite).
        self.params = validated  # type: ignore[assignment]
        return self


class TransformConfig(BaseModel):
    """
    Racine attendue de transformations.yaml.

    Supporte 2 formes :
    A) { "steps": [ ... ] }
    B) { "transformations": { "steps": [ ... ] } } (tolérance)
    """
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
    """
    Parseur transformations :
    - Convertit le DSL (dict à 1 clé) -> steps normalisés op/params
    - Valide strictement via Pydantic
    """

    def parse(self, raw: Dict[str, Any]) -> TransformConfig:
        converted = self._convert_steps(raw)
        return TransformConfig.model_validate(converted)

    def _convert_steps(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convertit les steps DSL "dict 1 clé" vers TransformStep(op, params).

        Input:
          {"steps":[ {"select":{"columns":["id"]}}, {"filter":{"expr":"id>1"}} ]}

        Output:
          {"steps":[ {"op":"select","params":{"columns":["id"]}}, {"op":"filter","params":{"expr":"id>1"}} ]}
        """
        data = raw

        # Tolérance wrapper : transformations: { steps: [...] }
        if "steps" not in data and "transformations" in data and isinstance(data["transformations"], dict):
            data = {"steps": data["transformations"].get("steps")}

        steps = data.get("steps")
        if not isinstance(steps, list):
            raise ValueError("steps doit être une liste")

        converted_steps: List[Dict[str, Any]] = []

        for idx, step in enumerate(steps, start=1):
            if not isinstance(step, dict) or len(step) != 1:
                raise ValueError(
                    f"Step #{idx} invalide: chaque step doit être un dict à 1 seule clé (opération)"
                )

            op = next(iter(step.keys()))
            params = step[op]

            if op not in _OP_MODEL_MAP:
                raise ValueError(f"Opération inconnue: {op}")

            if not isinstance(params, dict):
                raise ValueError(f"Step '{op}' invalide: les paramètres doivent être un dictionnaire")

            converted_steps.append({"op": op, "params": params})

        return {"steps": converted_steps}
