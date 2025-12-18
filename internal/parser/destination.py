"""
Parser + validation Pydantic pour destinations.yaml (Hydra DSL v1.1).

Rôle :
- Valider la structure de destinations.yaml
- Normaliser des valeurs par défaut (ex: batch_size, mode)
- Retourner une structure typée : DestinationsConfig

Non-responsabilités :
- Pas de connexion DB
- Pas d'exécution
- Pas de logique de pipeline (c'est pipeline.py)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class LoadConfig(BaseModel):
    """
    Configuration de chargement.

    MVP :
    - table obligatoire
    - mode : append | replace | upsert | truncate_then_load
      (au MVP, l'executor peut supporter seulement append/replace, mais on valide déjà le DSL)
    - key : obligatoire si mode=upsert
    """
    table: str = Field(min_length=1)
    mode: str = Field(default="append")
    batch_size: int = Field(default=10_000, ge=1)
    key: Optional[List[str]] = None

    @field_validator("table")
    @classmethod
    def _strip_table(cls, v: str) -> str:
        v2 = v.strip()
        if not v2:
            raise ValueError("table ne peut pas être vide")
        return v2

    @field_validator("mode")
    @classmethod
    def _normalize_mode(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("batch_size")
    @classmethod
    def _batch_size_reasonable(cls, v: int) -> int:
        if v < 10:
            raise ValueError("batch_size trop petit (minimum recommandé: 10)")
        return v

    @model_validator(mode="after")
    def _check_mode_and_key(self):
        allowed = {"append", "replace", "upsert", "truncate_then_load"}
        if self.mode not in allowed:
            raise ValueError(f"mode invalide: {self.mode} (attendu: {sorted(allowed)})")

        if self.mode == "upsert":
            if not self.key or not all(k.strip() for k in self.key):
                raise ValueError("mode=upsert exige 'key' (liste de colonnes non vides)")

        return self


class DestinationDefinition(BaseModel):
    """
    Définition d'une destination.

    Exemples de type :
    - mysql
    - mariadb
    - csv
    - json
    """
    type: str = Field(min_length=1)
    connection: Dict[str, Any] = Field(default_factory=dict)
    load: LoadConfig

    @field_validator("type")
    @classmethod
    def _normalize_type(cls, v: str) -> str:
        return v.strip().lower()


class DestinationsConfig(BaseModel):
    """
    Racine du fichier destinations.yaml.
    """
    destinations: Dict[str, DestinationDefinition] = Field(default_factory=dict)

    @field_validator("destinations")
    @classmethod
    def _at_least_one_destination(cls, v: Dict[str, DestinationDefinition]) -> Dict[str, DestinationDefinition]:
        if not v:
            raise ValueError("destinations.yaml ne contient aucune destination")
        return v


class DestinationParser:
    """
    Parser orienté "fichier" : prend un dict YAML déjà chargé et le valide.
    """

    def parse(self, raw: Dict[str, Any]) -> DestinationsConfig:
        """
        Valide et retourne DestinationsConfig.
        """
        return DestinationsConfig.model_validate(raw)
