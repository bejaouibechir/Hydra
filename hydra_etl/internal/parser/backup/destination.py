"""
Parser pour destinations.yaml.

Version Sprint 1 - Backlog 1.2:
- Ajout LoadMode Enum (append, replace, upsert)
- Validation stricte mode upsert → key obligatoire
- Nettoyage et validation colonnes key
- Messages d'erreur avec exemples
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional
from enum import Enum
from pydantic import BaseModel, Field, field_validator, model_validator


# ============================================================
# LoadMode Enum - Évite typos et facilite validation
# ============================================================

class LoadMode(str, Enum):
    """
    Modes de chargement supportés.
    
    - append: Ajoute les données (INSERT)
    - replace: Efface puis insère (TRUNCATE + INSERT)
    - upsert: Insert ou update si clé existe (INSERT ... ON DUPLICATE KEY UPDATE)
    """
    APPEND = "append"
    REPLACE = "replace"
    UPSERT = "upsert"


# ============================================================
# LoadConfig - Configuration section load
# ============================================================

class LoadConfig(BaseModel):
    """
    Configuration de chargement (section load dans destinations.yaml).
    
    Champs:
    - table: Nom de la table/fichier cible
    - mode: Mode de chargement (append|replace|upsert)
    - key: Colonnes clé (obligatoire si mode=upsert)
    - batch_size: Taille des batchs (défaut: 10 000)
    
    Validation stricte:
    - mode upsert → key obligatoire et non vide
    - key peut être clé simple [id] ou composite [region, product_id]
    
    Exemples:
        # Append simple
        load:
          table: orders
          mode: append
        
        # Upsert clé simple
        load:
          table: users
          mode: upsert
          key: [id]
        
        # Upsert clé composite
        load:
          table: sales
          mode: upsert
          key: [region, product_id]
    """
    
    table: str = Field(..., min_length=1)
    mode: LoadMode = Field(default=LoadMode.APPEND)
    key: Optional[List[str]] = Field(default=None, min_length=1)
    batch_size: int = Field(default=10_000, ge=10, le=100_000)
    
    @field_validator("table")
    @classmethod
    def _strip_table(cls, v: str) -> str:
        """Nettoie le nom de table."""
        v2 = v.strip()
        if not v2:
            raise ValueError("table cannot be empty")
        return v2
    
    @field_validator("key")
    @classmethod
    def clean_key_columns(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """
        Nettoie et valide colonnes de clé.
        
        - Trim whitespace
        - Rejette strings vides
        - Déduplique (conserve ordre)
        
        Exemples:
            ["id"] → ["id"]
            ["id", " name "] → ["id", "name"]
            ["id", "id"] → ["id"]  (dédupliqué)
            ["", "id"] → ValueError
        """
        if v is None:
            return None
        
        cleaned = []
        seen = set()
        
        for col in v:
            if not isinstance(col, str):
                raise ValueError(
                    f"key column must be string, got {type(col).__name__}"
                )
            
            col_clean = col.strip()
            
            if not col_clean:
                raise ValueError(
                    "key columns cannot be empty strings. "
                    "Example: key: [id] or key: [region, product_id]"
                )
            
            # Déduplication (garde premier ordre)
            if col_clean not in seen:
                cleaned.append(col_clean)
                seen.add(col_clean)
        
        if not cleaned:
            raise ValueError(
                "key list cannot be empty after cleaning. "
                "Provide at least one column name."
            )
        
        return cleaned
    
    @field_validator("batch_size")
    @classmethod
    def _batch_size_reasonable(cls, v: int) -> int:
        """Valide que batch_size est raisonnable."""
        if v < 10:
            raise ValueError(
                f"batch_size too small ({v}). Minimum recommended: 10"
            )
        if v > 100_000:
            raise ValueError(
                f"batch_size too large ({v}). Maximum recommended: 100 000"
            )
        return v
    
    @model_validator(mode="after")
    def validate_upsert_requires_key(self):
        """
        Validation cross-champs : mode upsert nécessite key.
        
        Cette validation se déclenche APRÈS tous les field_validator.
        
        Exemples valides:
            mode: append, key: null → OK
            mode: upsert, key: [id] → OK
            mode: upsert, key: [region, product_id] → OK
        
        Exemples invalides:
            mode: upsert, key: null → ValueError
            mode: upsert, key: [] → ValueError
        
        Raises:
            ValueError: Si mode upsert sans key
        """
        if self.mode == LoadMode.UPSERT:
            if not self.key:
                raise ValueError(
                    "mode 'upsert' requires 'key' parameter. "
                    "Specify primary key or unique key columns.\n"
                    "Examples:\n"
                    "  key: [id]                    # Simple key\n"
                    "  key: [region, product_id]    # Composite key"
                )
        
        return self


# ============================================================
# DestinationDefinition
# ============================================================

class DestinationDefinition(BaseModel):
    """
    Définition d'une destination.
    
    Exemples de type:
    - mysql
    - mariadb
    - csv
    - postgresql (futur)
    """
    type: str = Field(..., min_length=1)
    connection: Dict[str, Any] = Field(default_factory=dict)
    load: LoadConfig
    
    @field_validator("type")
    @classmethod
    def _normalize_type(cls, v: str) -> str:
        """Normalise type en lowercase."""
        return v.strip().lower()


# ============================================================
# DestinationsConfig - Racine YAML
# ============================================================

class DestinationsConfig(BaseModel):
    """
    Racine du fichier destinations.yaml.
    
    Exemple:
        destinations:
          dest_dwh:
            type: mysql
            connection: {...}
            load:
              table: orders
              mode: upsert
              key: [id]
    """
    destinations: Dict[str, DestinationDefinition] = Field(
        ...,
        min_length=1
    )
    
    @field_validator("destinations")
    @classmethod
    def _no_empty_destinations(cls, v: Dict[str, DestinationDefinition]):
        """Vérifie que destinations n'est pas vide."""
        if not v:
            raise ValueError(
                "destinations cannot be empty. "
                "Define at least one destination."
            )
        return v


# ============================================================
# Parser - Point d'entrée
# ============================================================

class DestinationParser:
    """
    Parser pour destinations.yaml.
    
    Usage:
        parser = DestinationParser()
        config = parser.parse(yaml_dict)
    """
    
    def parse(self, raw: Dict[str, Any]) -> DestinationsConfig:
        """
        Parse et valide le fichier destinations.yaml.
        
        Args:
            raw: Dict depuis YAML (via yaml.safe_load)
        
        Returns:
            DestinationsConfig validé
        
        Raises:
            ValidationError: Si structure invalide
        
        Exemple:
            >>> raw = {
            ...     "destinations": {
            ...         "dest_db": {
            ...             "type": "mysql",
            ...             "connection": {"host": "localhost"},
            ...             "load": {
            ...                 "table": "users",
            ...                 "mode": "upsert",
            ...                 "key": ["id"]
            ...             }
            ...         }
            ...     }
            ... }
            >>> cfg = DestinationParser().parse(raw)
            >>> cfg.destinations["dest_db"].load.mode
            <LoadMode.UPSERT: 'upsert'>
        """
        return DestinationsConfig(**raw)