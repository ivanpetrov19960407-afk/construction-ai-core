"""RAG endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from core.rag_engine import RAGEngine

router = APIRouter()
rag_engine = RAGEngine()


@router.get("/stats")
async def rag_stats(role: str = Query(default="pto_engineer")) -> dict:
    """Вернуть статистику RAG (доступно только admin)."""
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return rag_engine.get_stats()
