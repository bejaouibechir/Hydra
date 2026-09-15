"""Compatibilité — les garde-fous vivent désormais dans le produit.

Ils ont quitté le banc d'essai pour `hydra_etl/ai/guards.py`, où le Studio,
l'API et le serveur MCP les partagent. Ce module ne fait plus que réexporter,
afin que ce qui est mesuré soit exactement ce qui est livré.
"""

from hydra_etl.ai.guards import *          # noqa: F401,F403
from hydra_etl.ai.guards import check      # noqa: F401
