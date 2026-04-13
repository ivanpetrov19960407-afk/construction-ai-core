"""RAG endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from config.settings import settings
from core.rag_engine import RAGEngine

router = APIRouter()
rag_engine = RAGEngine()


@router.get("/stats")
async def rag_stats(request: Request) -> dict:
    """Вернуть статистику RAG (доступно только admin)."""
    api_key = request.headers.get("X-API-Key")
    if not api_key or api_key not in settings.admin_api_keys:
        raise HTTPException(status_code=403, detail="Admin role required")
    return rag_engine.get_stats()
