"""RAG endpoints."""

from __future__ import annotations

from functools import lru_cache
from io import BytesIO
from tempfile import NamedTemporaryFile

from docx import Document
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from typing_extensions import TypedDict

from config.settings import settings
from core.pdf_parser import PDFParser
from core.rag_engine import RAGEngine

DOCX_MIME_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

router = APIRouter()
pdf_parser = PDFParser()


@lru_cache(maxsize=1)
def get_rag_engine() -> RAGEngine:
    return RAGEngine()


def _require_admin(request: Request) -> None:
    user_role = getattr(request.state, "user_role", None)
    if user_role == "admin":
        return
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
    session_id: str | None = Form(None),
) -> dict[str, int | str]:
    """Загрузить PDF/DOCX в RAG-индекс (доступно только admin)."""
    _require_admin(request)
    filename = file.filename or source_name
    is_pdf = file.content_type == "application/pdf" or filename.lower().endswith(".pdf")
    is_docx = file.content_type == DOCX_MIME_TYPE or filename.lower().endswith(".docx")
    if not is_pdf and not is_docx:
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files are supported")

    file_bytes = await file.read()
    metadata = {"session_id": session_id} if session_id else None

    if is_pdf:
        pdf_parser.parse(file_bytes, filename=filename)

        with NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
            tmp.write(file_bytes)
            tmp.flush()
            chunks_added = get_rag_engine().ingest_pdf(
                tmp.name,
                source_name=source_name,
                metadata=metadata,
            )
    else:
        document = Document(BytesIO(file_bytes))
        text = "\n".join(
            paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()
        )
        if not text.strip():
            raise HTTPException(status_code=400, detail="DOCX does not contain text")
        chunks_added = get_rag_engine().ingest_text(
            text,
            source_name=source_name,
            metadata=metadata,
        )

    return {"chunks_added": int(chunks_added), "source": source_name}


class SourceSummary(TypedDict):
    source: str
    chunks: int


@router.get("/sources")
async def rag_sources(request: Request) -> dict[str, list[SourceSummary]]:
    """Вернуть список источников RAG с количеством чанков (доступно только admin)."""
    _require_admin(request)
    payload = get_rag_engine().collection.get(include=["metadatas"])
    metadatas = payload.get("metadatas") or []
    counters: dict[str, int] = {}
    for meta in metadatas:
        source = str((meta or {}).get("source", "unknown"))
        counters[source] = counters.get(source, 0) + 1

    sources: list[SourceSummary] = [
        SourceSummary(source=source, chunks=count) for source, count in sorted(counters.items())
    ]
    return {"sources": sources}
