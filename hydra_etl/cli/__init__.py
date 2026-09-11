"""
Package CLI Hydra.

Point d'entrée : hydra_etl.cli.hdrctl:main
Commandes : hydra / hdrctl (voir [project.scripts] dans pyproject.toml)

Règle 3.1 : la version vient de hydra_etl/__init__.py. Ce module la ré-exporte
pour compatibilité, il ne la définit pas.
"""

from hydra_etl import __version__

__all__ = ["__version__"]
