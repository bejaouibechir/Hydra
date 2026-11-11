"""
Modèle de `pipeline.yaml`.

Ce manifeste est le seul des quatre qui n'avait pas de modèle Pydantic : il
était lu de façon ad hoc. Ce module comble ce trou afin que la spécification du
DSL puisse être générée depuis le code, comme pour les trois autres.

Portée actuelle : **spécification et validation de schéma**. Le modèle n'est pas
encore branché dans l'exécuteur ; le brancher est une étape de suivi
(cf. `tools/spec_export.py`).

Clés réellement exigées par l'exécuteur : `pipeline.from` et `pipeline.to`.
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class PipelineDefinition(BaseModel):
    """Connects a declared source to a declared destination."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    name: Optional[str] = Field(
        default=None,
        description="Nom du pipeline. Facultatif.",
    )
    from_: str = Field(
        alias="from",
        description="Identifier declared in sources.yaml.",
    )
    to: str = Field(
        description="Identifier declared in destinations.yaml.",
    )
    transformations: Optional[str] = Field(
        default=None,
        description=(
            "Reference to the transformations manifest. Optional: "
            "without it, transformations.yaml is used if it exists."
        ),
    )


class PipelineConfig(BaseModel):
    """Contenu complet de `pipeline.yaml`."""

    model_config = ConfigDict(extra="forbid")

    version: str = Field(default="1.0", description="Version du manifeste.")
    pipeline: PipelineDefinition
