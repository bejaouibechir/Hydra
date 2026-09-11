"""
Types publics Hydra ETL.

But :
- Offrir une API stable côté utilisateur (CLI / intégrations).
- Éviter d'exposer les classes internes (executor, parser, connecteurs...).

Règle :
- Tout ce qui est ici est "public" et doit rester rétro-compatible autant que possible.

Version : 1.1 (Étape 5 - MVP Executor)
Corrections appliquées :
- ✅ Suppression duplication (DetailedJobResult, StepStats, JobStatus)
- ✅ Garde uniquement JobResult MVP
- ✅ Documentation claire des extensions futures
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------
# Étape 5 — JobResult MVP (ce que l'executor minimal renverra)
# ---------------------------------------------------------------------


@dataclass
class JobResult:
    """
    Résultat d'exécution d'un job ETL (MVP Étape 5).
    
    Attributs :
        success (bool) : 
            True si le job a terminé sans erreur (mode fail-fast).
            False si une erreur a provoqué l'arrêt du job.
        
        rows_in (int) : 
            Nombre total de lignes lues depuis la source (avant transformations).
            Correspond à la somme de toutes les lignes de tous les batches extraits.
        
        rows_out (int) : 
            Nombre total de lignes écrites dans la destination (après transformations).
            Peut être différent de rows_in si des filtres ont éliminé des lignes.
        
        duration (float) : 
            Temps total d'exécution en secondes (time.monotonic).
            Inclut extraction + transformation + chargement.
        
        error (Optional[str]) : 
            Message d'erreur si success=False, None sinon.
            Contient la description de l'exception qui a provoqué l'échec.
    
    Exemple d'utilisation :
        >>> from internal.runner.executor import JobExecutor
        >>> executor = JobExecutor(job_dir="jobs/my_job")
        >>> result = executor.run()
        >>> if result.success:
        ...     print(f"✅ Job terminé : {result.rows_out} lignes en {result.duration:.2f}s")
        ... else:
        ...     print(f"❌ Job échoué : {result.error}")
    
    Extensions futures (post-MVP) :
        Ces attributs pourront être ajoutés sans casser la compatibilité :
        - steps: List[StepStats] pour statistiques détaillées par étape
        - job_id: str pour identification/tracking
        - metadata: Dict[str, Any] pour informations contextuelles
        - warnings: List[str] pour avertissements non-bloquants
    """
    
    success: bool
    rows_in: int
    rows_out: int
    duration: float
    error: Optional[str] = None
    output_sample: List[Dict[str, Any]] = field(default_factory=list)
    output_columns: List[str] = field(default_factory=list)
    
    def __str__(self) -> str:
        """Représentation lisible du résultat."""
        if self.success:
            return (
                f"JobResult(✅ SUCCESS | "
                f"rows: {self.rows_in}→{self.rows_out} | "
                f"duration: {self.duration:.2f}s)"
            )
        else:
            return (
                f"JobResult(❌ FAILED | "
                f"rows: {self.rows_in}→{self.rows_out} | "
                f"duration: {self.duration:.2f}s | "
                f"error: {self.error})"
            )
    
    def to_dict(self) -> dict:
        """Convertit en dictionnaire (utile pour sérialisation JSON)."""
        return {
            "success": self.success,
            "rows_in": self.rows_in,
            "rows_out": self.rows_out,
            "duration": self.duration,
            "error": self.error,
            "output_sample": self.output_sample,
            "output_columns": self.output_columns,
        }


# ---------------------------------------------------------------------
# Types futurs (post-MVP, commentés pour référence)
# ---------------------------------------------------------------------

# @dataclass
# class StepStats:
#     """
#     Statistiques détaillées d'une étape de transformation (post-MVP).
#     """
#     step_index: int
#     operation: str
#     rows_in: int
#     rows_out: int
#     duration: float
#     details: Dict[str, Any] = field(default_factory=dict)

# @dataclass
# class DetailedJobResult(JobResult):
#     """
#     Résultat enrichi avec détails par étape (post-MVP).
#     Hérite de JobResult pour compatibilité.
#     """
#     steps: List[StepStats] = field(default_factory=list)
#     job_id: str = ""
#     metadata: Dict[str, Any] = field(default_factory=dict)