"""api/routers/health.py — Health check.

Expose la version produit lue depuis hydra_etl/__init__.py (Règle 3.1) :
c'est la source que le pied de page du Studio consomme, afin qu'aucun
littéral de version ne soit recopié côté front.
"""
from fastapi import APIRouter

from hydra_etl import DSL_VERSION, __version__

router = APIRouter()


@router.get("/api/health")
def health_check():
    """Vérifie que l'API est opérationnelle et annonce versions et Studio."""
    from hydra_etl.api.studio import studio_status

    return {
        "message": "Hydra ETL API is running",
        "status": "ok",
        "version": __version__,
        "dsl_version": DSL_VERSION,
        # bundled | missing | disabled — permet de diagnostiquer une page
        # blanche ou un 404 sur / avec une seule requete.
        "studio": studio_status(),
    }
