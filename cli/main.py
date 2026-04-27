"""
CLI Hydra (MVP - Étape 6)

Commande supportée :
    hydra run <job_dir>

Architecture :
- Wrapper ultra-fin autour de JobExecutor existant
- Aucune logique métier dans la CLI
- Affichage simple et lisible des résultats

Prérequis :
- JobExecutor (internal/runner/executor.py) ✅
- JobResult (etl/types.py) ✅
- Parsers DSL ✅
- ConfigLoader ✅

Version : 1.0 (MVP)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import NoReturn

from etl.types import JobResult
from internal.runner.executor import JobExecutor


def print_banner() -> None:
    """Affiche le banner Hydra."""
    print("=" * 60)
    print("🚀 HYDRA ETL Framework - MVP")
    print("=" * 60)


def print_report(result: JobResult, job_dir: Path) -> None:
    """
    Affiche un rapport lisible du résultat d'exécution.
    
    Args:
        result: Résultat retourné par JobExecutor
        job_dir: Chemin du job exécuté
    """
    print("\n" + "─" * 60)
    print("📊 RAPPORT D'EXÉCUTION")
    print("─" * 60)
    
    print(f"📁 Job         : {job_dir.name}")
    print(f"📂 Chemin      : {job_dir}")
    
    # Status avec emoji
    if result.success:
        print(f"✅ Statut      : SUCCESS")
    else:
        print(f"❌ Statut      : FAILED")
    
    # Métriques
    print(f"📥 Lignes in   : {result.rows_in:,}")
    print(f"📤 Lignes out  : {result.rows_out:,}")
    print(f"⏱️  Durée       : {result.duration:.3f}s")
    
    # Erreur si présente
    if result.error:
        print(f"\n💥 Erreur :")
        print(f"   {result.error}")
    
    print("─" * 60)


def run_job(job_dir_str: str) -> int:
    """
    Exécute un job Hydra.
    
    Args:
        job_dir_str: Chemin du répertoire job (string)
    
    Returns:
        Code de sortie : 0 si succès, 1 si échec
    """
    # Validation du chemin
    job_dir = Path(job_dir_str).resolve()
    
    if not job_dir.exists():
        print(f"❌ ERREUR : Le répertoire '{job_dir}' n'existe pas")
        return 1
    
    if not job_dir.is_dir():
        print(f"❌ ERREUR : '{job_dir}' n'est pas un répertoire")
        return 1
    
    # Vérification fichiers requis
    required_files = ["sources.yaml", "destinations.yaml", "pipeline.yaml"]
    missing_files = [f for f in required_files if not (job_dir / f).exists()]
    
    if missing_files:
        print(f"❌ ERREUR : Fichiers manquants dans {job_dir.name}:")
        for f in missing_files:
            print(f"   - {f}")
        return 1
    
    # Exécution du job
    print(f"\n🚀 Lancement du job : {job_dir.name}")
    print(f"📂 Répertoire : {job_dir}")
    print()
    
    try:
        # Instanciation de l'executor
        # JobExecutor gère automatiquement :
        # - Chargement des .env (root + job)
        # - Parsing des YAML
        # - Résolution ${ENV:...}
        # - Exécution du pipeline
        executor = JobExecutor(job_dir=job_dir)
        
        # Exécution (mode fail-fast)
        result = executor.run()
        
        # Affichage du rapport
        print_report(result, job_dir)
        
        # Code de sortie
        return 0 if result.success else 1
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Interruption utilisateur (Ctrl+C)")
        return 130  # Code standard UNIX pour SIGINT
        
    except Exception as e:
        # Erreur non gérée par JobExecutor
        print("\n" + "─" * 60)
        print("💥 ERREUR CRITIQUE")
        print("─" * 60)
        print(f"Type  : {type(e).__name__}")
        print(f"Message : {e}")
        print("─" * 60)
        return 1


def main(argv: list[str] | None = None) -> NoReturn:
    """
    Point d'entrée principal de la CLI.
    
    Args:
        argv: Arguments (pour tests), None = utilise sys.argv
    """
    # Parser d'arguments
    parser = argparse.ArgumentParser(
        prog="hydra",
        description="Hydra ETL Framework - Exécution de jobs ETL déclaratifs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  hydra run jobs/my_job          # Exécute le job dans jobs/my_job/
  hydra run examples/csv_demo    # Exécute l'exemple CSV

Structure attendue d'un job:
  my_job/
  ├── sources.yaml          (requis)
  ├── destinations.yaml     (requis)
  ├── pipeline.yaml         (requis)
  ├── transformations.yaml  (optionnel)
  └── .env                  (optionnel)
        """
    )
    
    # Sous-commandes
    subparsers = parser.add_subparsers(dest="command", help="Commande à exécuter")
    
    # Commande : run
    run_parser = subparsers.add_parser(
        "run",
        help="Exécute un job ETL",
        description="Exécute un job ETL depuis un répertoire contenant les YAML de configuration"
    )
    run_parser.add_argument(
        "job_dir",
        type=str,
        help="Chemin du répertoire contenant le job (sources.yaml, etc.)"
    )
    
    # Parse
    args = parser.parse_args(argv)
    
    # Vérification commande
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Banner
    print_banner()
    
    # Exécution
    if args.command == "run":
        exit_code = run_job(args.job_dir)
        sys.exit(exit_code)
    
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()