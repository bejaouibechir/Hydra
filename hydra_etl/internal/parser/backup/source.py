"""
Parser + validation Pydantic pour sources.yaml (Hydra DSL v1.1).

Rôle :
- Valider la structure de sources.yaml
- Normaliser des valeurs par défaut (ex: batch_size)
- Retourner une structure typée : SourcesConfig

Non-responsabilités :
- Pas de connexion DB
- Pas d'exécution
- Pas de logique de pipeline (c'est pipeline.py)
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator


class ExtractConfig(BaseModel):
    """
    Décrit comment extraire depuis une source.

    MVP :
    - soit table
    - soit query
    """
    table: Optional[str] = None
    query: Optional[str] = None
    batch_size: int = Field(default=10_000, ge=1)

    @field_validator("query")
    @classmethod
    def _strip_query(cls, v: Optional[str]) -> Optional[str]:
        # Nettoyage simple : éviter query = "   "
        if v is not None:
            v2 = v.strip()
            return v2 if v2 else None
        return v

    @field_validator("table")
    @classmethod
    def _strip_table(cls, v: Optional[str]) -> Optional[str]:
        # Nettoyage simple : éviter table = "   "
        if v is not None:
            v2 = v.strip()
            return v2 if v2 else None
        return v

    @field_validator("batch_size")
    @classmethod
    def _batch_size_reasonable(cls, v: int) -> int:
        # Garde-fou MVP (évite batch_size=1 accidentel)
        if v < 10:
            raise ValueError("batch_size trop petit (minimum recommandé: 10)")
        return v

    @model_validator(mode="after")
    def _check_table_or_query(self):
        # Validation croisée : au moins table ou query
        if not self.table and not self.query:
            raise ValueError("extract doit définir 'table' ou 'query'")
        return self


class SourceDefinition(BaseModel):
    """
    Définition d'une source.

    Exemples de type :
    - mysql
    - mariadb
    - csv
    - json
    """
    type: str = Field(min_length=1)
    connection: Dict[str, Any] = Field(default_factory=dict)
    extract: ExtractConfig

    @field_validator("type")
    @classmethod
    def _normalize_type(cls, v: str) -> str:
        # Normalisation simple : "MySQL" -> "mysql"
        return v.strip().lower()


class SourcesConfig(BaseModel):
    """
    Racine du fichier sources.yaml.
    """
    sources: Dict[str, SourceDefinition] = Field(default_factory=dict)

    @field_validator("sources")
    @classmethod
    def _at_least_one_source(cls, v: Dict[str, SourceDefinition]) -> Dict[str, SourceDefinition]:
        if not v:
            raise ValueError("sources.yaml ne contient aucune source")
        return v


class SourceParser:
    """
    Parser orienté "fichier" : prend un dict YAML déjà chargé et le valide.
    """

    def parse(self, raw: Dict[str, Any]) -> SourcesConfig:
        """
        Valide et retourne SourcesConfig.
        """
        return SourcesConfig.model_validate(raw)
