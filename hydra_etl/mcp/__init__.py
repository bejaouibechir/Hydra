"""Serveur MCP local de Hydra — expose le moteur à un agent IA.

Le serveur ne contient aucun modèle et ne fait aucun appel réseau : MCP est un
protocole, l'intelligence vient du client (Claude Desktop, Cursor, VS Code,
Hydra Studio…). Voir `hydra_etl/mcp/server.py`.
"""

from hydra_etl.mcp.server import build_server, main

__all__ = ["build_server", "main"]
