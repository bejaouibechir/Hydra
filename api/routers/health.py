"""api/routers/health.py — Health check."""
from fastapi import APIRouter
from api.models import MessageResponse

router = APIRouter()

@router.get("/api/health", response_model=MessageResponse)
def health_check():
    """Vérifie que l'API est opérationnelle."""
    return {"message": "Hydra ETL API is running"}
