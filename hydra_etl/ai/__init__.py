"""Couche IA de Hydra — partagée par le Studio, l'API et le serveur MCP.

Ce qui vit ici est ce qui est mesuré par `eval/run_eval.py` : une copie
divergerait, et l'on mesurerait alors autre chose que ce que l'on livre.
"""

from hydra_etl.ai.guards import check

__all__ = ["check"]
