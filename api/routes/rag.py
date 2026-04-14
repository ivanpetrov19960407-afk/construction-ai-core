"""RAG endpoints."""

from __future__ import annotations

from functools import lru_cache
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from config.settings import settings
from core.pdf_parser import PDFParser
from core.rag_engine import RAGEngine

router = APIRouter()
pdf_parser = PDFParser()


@lru_cache(maxsize=1)
def get_rag_engine() -> RAGEngine:
    return RAGEngine()


def _require_admin(request: Request) -> None:
    api_key = request.headers.get("X-API-Key")
    if not api_key or api_key not in settings.admin_api_keys:
        raise HTTPException(status_code=403, detail="Admin role required")


@router.get("/stats")
async def rag_stats(request: Request) -> dict:
    """Вернуть статистику RAG (доступно только admin)."""
    _require_admin(request)
    return get_rag_engine().get_stats()


@router.post("/ingest")
async def rag_ingest(
    request: Request,
    file: UploadFile = File(...),
    source_name: str = Form(...),
) -> dict[str, int | str]:
    """Загрузить PDF в RAG-индекс (доступно только admin)."""
    _require_admin(request)
    filename = file.filename or source_name
    if file.content_type != "application/pdf" and not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    file_bytes = await file.read()
    pdf_parser.parse(file_bytes, filename=filename)

    with NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
        tmp.write(file_bytes)
        tmp.flush()
        chunks_added = get_rag_engine().ingest_pdf(tmp.name, source_name=source_name)
    return {"chunks_added": int(chunks_added), "source": source_name}


@router.get("/sources")
async def rag_sources(request: Request) -> dict[str, list[dict[str, int | str]]]:
    """Вернуть список источников RAG с количеством чанков (доступно только admin)."""
    _require_admin(request)
    payload = get_rag_engine().collection.get(include=["metadatas"])
    metadatas = payload.get("metadatas") or []
    counters: dict[str, int] = {}
    for meta in metadatas:
        source = str((meta or {}).get("source", "unknown"))
        counters[source] = counters.get(source, 0) + 1

    sources = [{"source": source, "chunks": count} for source, count in sorted(counters.items())]
    return {"sources": sources}
