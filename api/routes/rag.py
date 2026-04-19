"""RAG endpoints."""

from __future__ import annotations

from functools import lru_cache
from hashlib import sha256
from io import BytesIO
from tempfile import NamedTemporaryFile
from urllib.parse import unquote
from zipfile import BadZipFile

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


def _resolve_actor(request: Request) -> str:
    username = getattr(request.state, "username", None)
    if username:
        return str(username)
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return f"api-key:{sha256(api_key.encode('utf-8')).hexdigest()}"
    raise HTTPException(status_code=401, detail="Authentication required")


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
    return _ingest_uploaded_file(file=file, source_name=source_name, session_id=session_id)


@router.post("/chat-upload")
async def rag_chat_upload(
    request: Request,
    file: UploadFile = File(...),
    session_id: str = Form(...),
    source_name: str | None = Form(None),
) -> dict[str, int | str]:
    """Загрузить файл из чата в RAG-индекс для текущей session_id."""
    actor = _resolve_actor(request)
    effective_source_name = source_name or file.filename or f"chat-{session_id}.doc"
    return _ingest_uploaded_file(
        file=file,
        source_name=effective_source_name,
        session_id=session_id,
        actor=actor,
    )


def _ingest_uploaded_file(
    *,
    file: UploadFile,
    source_name: str,
    session_id: str | None,
    actor: str | None = None,
) -> dict[str, int | str]:
    filename = file.filename or source_name
    is_pdf = file.content_type == "application/pdf" or filename.lower().endswith(".pdf")
    is_docx = file.content_type == DOCX_MIME_TYPE or filename.lower().endswith(".docx")
    if not is_pdf and not is_docx:
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files are supported")

    file_bytes = file.file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    metadata: dict[str, str] | None = None
    if session_id or actor:
        metadata = {}
        if session_id:
            metadata["session_id"] = session_id
        if actor:
            metadata["username"] = actor

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
        try:
            document = Document(BytesIO(file_bytes))
        except (BadZipFile, ValueError) as exc:
            raise HTTPException(status_code=400, detail="Invalid DOCX file") from exc
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


@router.get("/my-sources")
async def rag_my_sources(request: Request) -> dict[str, list[SourceSummary]]:
    """Вернуть источники, загруженные текущим пользователем."""
    actor = _resolve_actor(request)
    payload = get_rag_engine().collection.get(include=["metadatas"])
    metadatas = payload.get("metadatas") or []
    counters: dict[str, int] = {}
    for meta in metadatas:
        current = meta or {}
        if str(current.get("username", "")) != actor:
            continue
        source = str(current.get("source", "unknown"))
        counters[source] = counters.get(source, 0) + 1

    sources: list[SourceSummary] = [
        SourceSummary(source=source, chunks=count) for source, count in sorted(counters.items())
    ]
    return {"sources": sources}


@router.delete("/sources/{source_name:path}")
async def rag_delete_source(source_name: str, request: Request) -> dict[str, int | str]:
    """Удалить источник целиком (доступно только admin)."""
    _require_admin(request)
    decoded_source_name = unquote(source_name)
    payload = get_rag_engine().collection.get(include=["metadatas"])
    ids = payload.get("ids") or []
    metadatas = payload.get("metadatas") or []
    matched_ids = [
        str(doc_id)
        for doc_id, meta in zip(ids, metadatas, strict=False)
        if str((meta or {}).get("source", "")) == decoded_source_name
    ]
    if not matched_ids:
        return {"deleted": 0, "source": decoded_source_name}

    get_rag_engine().collection.delete(ids=matched_ids)
    return {"deleted": len(matched_ids), "source": decoded_source_name}
