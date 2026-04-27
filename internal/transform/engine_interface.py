"""
Contrat standard des moteurs de transformation SmartETL / Hydra.

But :
- Permettre de brancher plusieurs moteurs (pandas, duckdb, polars...)
  sans changer l'executor.
- Fournir une API minimale :
  - apply_step()     : applique une étape du DSL sur un "dataset"
  - apply_pipeline() : applique une liste ordonnée d'étapes

Notes :
- Le "dataset" est typé Any volontairement :
  - pandas : DataFrame
  - duckdb : relation / vue / nom de table temporaire
  - autre  : structure interne
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional


@dataclass(frozen=True)
class StepResult:
    """
    Résultat minimal d'une étape.

    On retourne à la fois :
    - output : le dataset produit (ou une référence vers celui-ci)
    - stats  : infos utiles pour métriques/debug
    """

    output: Any
    stats: Dict[str, Any]


class TransformEngine(ABC):
    """
    Interface commune à tous les moteurs de transformation.
    """

    def __init__(self, name: str = "engine") -> None:
        # name : utile pour logs (ex: "pandas", "duckdb")
        self.name = name

    @abstractmethod
    def apply_step(
        self,
        dataset: Any,
        step: Dict[str, Any],
        *,
        context: Optional[Dict[str, Any]] = None,
    ) -> StepResult:
        """
        Applique une étape unique du DSL.

        Paramètres :
        - dataset : entrée (DataFrame, relation DuckDB, etc.)
        - step    : dict normalisé (déjà validé par le parser)
        - context : infos runtime optionnelles (job_id, paramètres, etc.)

        Contrat :
        - lève une exception si l'étape est invalide ou échoue
        - retourne StepResult (output + stats)
        """
        raise NotImplementedError

    def apply_pipeline(
        self,
        dataset: Any,
        steps: Iterable[Dict[str, Any]],
        *,
        context: Optional[Dict[str, Any]] = None,
    ) -> StepResult:
        """
        Applique une séquence ordonnée d'étapes.

        Par défaut :
        - exécute step par step en appelant apply_step()
        - agrège des stats simples

        Un moteur peut override cette méthode pour optimiser :
        - fusion de steps
        - compilation
        - pushdown SQL
        """
        current = dataset
        aggregated_stats: Dict[str, Any] = {"steps": []}

        for index, step in enumerate(steps, start=1):
            result = self.apply_step(current, step, context=context)
            current = result.output

            # On garde un historique minimal pour debug/métriques
            aggregated_stats["steps"].append(
                {
                    "index": index,
                    "engine": self.name,
                    "step_type": self._infer_step_type(step),
                    "stats": result.stats,
                }
            )

        return StepResult(output=current, stats=aggregated_stats)

    @staticmethod
    def _infer_step_type(step: Dict[str, Any]) -> str:
        """
        Infère un type d'étape à des fins de logs.
        Exemple : {"select": {...}} -> "select"

        Le parser pourra fournir un champ "op" plus tard,
        mais on reste robuste même sans.
        """
        if not step:
            return "unknown"
        # Si le parser normalise en {"op": "select", ...} on le prend
        if "op" in step and isinstance(step["op"], str):
            return step["op"]
        # Sinon on prend la première clé "utile"
        for k in step.keys():
            return str(k)
        return "unknown"
