"""Health-check endpoint."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    """Проверка состояния сервиса."""
    return {
        "status": "ok",
        "service": "construction-ai-core",
        "version": "0.1.0",
    }
