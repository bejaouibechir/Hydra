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

import warnings
from typing import Any, Dict, Optional, List

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

# Le champ 'schema' dans SourceDefinition est intentionnel (DSL YAML).
# Le shadowing de BaseModel.schema est inoffensif en Pydantic v2 (methode supprimee).
warnings.filterwarnings(
    "ignore",
    message="Field name \"schema\" in \"SourceDefinition\" shadows an attribute",
    category=UserWarning,
)


# ============================================================
# Schema Config (pour MongoDB et sources atypiques)
# ============================================================

class SchemaFieldConfig(BaseModel):
    """Configuration d'un champ dans le schéma source."""
    name: str = Field(min_length=1)
    type: str = Field(min_length=1)
    path: Optional[str] = None
    required: bool = False
    default: Optional[Any] = None
    array_handling: Optional[str] = None
    description: Optional[str] = None
    
    @field_validator("type")
    @classmethod
    def _normalize_type(cls, v: str) -> str:
        return v.strip().lower()
    
    @field_validator("array_handling")
    @classmethod
    def _validate_array_handling(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip().lower()
        valid_options = ["keep", "flatten", "explode", "json"]
        if v not in valid_options:
            raise ValueError(f"array_handling must be one of {valid_options}, got '{v}'")
        return v


class SchemaConfig(BaseModel):
    """Configuration du schéma pour sources atypiques."""
    mode: str = Field(default="auto")
    fields: List[SchemaFieldConfig] = Field(default_factory=list)
    drift_policy: str = Field(default="warn")
    validation_policy: str = Field(default="best_effort")
    sample_size: int = Field(default=100, ge=1)
    
    @field_validator("mode")
    @classmethod
    def _validate_mode(cls, v: str) -> str:
        v = v.strip().lower()
        valid_modes = ["auto", "manual", "infer_strict", "hybrid"]
        if v not in valid_modes:
            raise ValueError(f"schema.mode must be one of {valid_modes}, got '{v}'")
        return v
    
    @field_validator("drift_policy")
    @classmethod
    def _validate_drift_policy(cls, v: str) -> str:
        v = v.strip().lower()
        valid_policies = ["fail", "warn", "ignore", "adapt"]
        if v not in valid_policies:
            raise ValueError(f"schema.drift_policy must be one of {valid_policies}, got '{v}'")
        return v
    
    @field_validator("validation_policy")
    @classmethod
    def _validate_validation_policy(cls, v: str) -> str:
        v = v.strip().lower()
        valid_policies = ["strict", "best_effort", "permissive"]
        if v not in valid_policies:
            raise ValueError(f"schema.validation_policy must be one of {valid_policies}, got '{v}'")
        return v


# ============================================================
# Extract Config
# ============================================================

class ExtractConfig(BaseModel):
    """
    Décrit comment extraire depuis une source.

    MVP :
    - soit table
    - soit query
    - soit collection (MongoDB)
    """
    table: Optional[str] = None
    query: Optional[str] = None
    collection: Optional[str] = None  # MongoDB
    filter: Optional[Dict[str, Any]] = None  # MongoDB filter
    limit: Optional[int] = None
    batch_size: int = Field(default=10_000, ge=1)

    @field_validator("query")
    @classmethod
    def _strip_query(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v2 = v.strip()
            return v2 if v2 else None
        return v

    @field_validator("table")
    @classmethod
    def _strip_table(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v2 = v.strip()
            return v2 if v2 else None
        return v
    
    @field_validator("collection")
    @classmethod
    def _strip_collection(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v2 = v.strip()
            return v2 if v2 else None
        return v

    @field_validator("batch_size")
    @classmethod
    def _batch_size_reasonable(cls, v: int) -> int:
        if v < 10:
            raise ValueError("batch_size trop petit (minimum recommandé: 10)")
        return v

    @model_validator(mode="after")
    def _check_table_or_query_or_collection(self):
        if not self.table and not self.query and not self.collection:
            raise ValueError("extract doit définir 'table', 'query' ou 'collection'")
        return self


# ============================================================
# Source Definition
# ============================================================

class SourceDefinition(BaseModel):
    """
    Définition d'une source.

    Exemples de type :
    - mysql
    - mariadb
    - mongodb
    - csv
    - json
    """
    model_config = {"protected_namespaces": ()}

    type: str = Field(min_length=1)
    connection: Dict[str, Any] = Field(default_factory=dict)
    extract: ExtractConfig
    schema: Optional[SchemaConfig] = None

    @field_validator("type")
    @classmethod
    def _normalize_type(cls, v: str) -> str:
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