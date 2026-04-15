"""Analyze endpoints — анализ тендерной документации."""

from __future__ import annotations

import asyncio
import tempfile
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from core.document_diff import DocumentDiff, read_text_file
from core.orchestrator import Orchestrator
from core.pdf_parser import PDFParser

router = APIRouter()
orchestrator = Orchestrator()
pdf_parser = PDFParser()
document_diff = DocumentDiff()

MAX_UPLOAD_SIZE_BYTES = 20 * 1024 * 1024
ANALYZE_TIMEOUT_SECONDS = 120


class TenderAnalysisRequest(BaseModel):
    session_id: str | None = None
    role: str = "tender_specialist"

    @classmethod
    def as_form(
        cls,
        session_id: Annotated[str | None, Form()] = None,
        role: Annotated[str, Form()] = "tender_specialist",
    ) -> TenderAnalysisRequest:
        return cls(session_id=session_id, role=role)


class TenderAnalysisResponse(BaseModel):
    session_id: str
    risks: list[str]
    contradictions: list[str]
    legal_issues: list[str]
    normative_refs: list[str]
    confidence: float
    recommendation: str


class DiffRequest(BaseModel):
    session_id_v1: str
    session_id_v2: str


class DiffResponse(BaseModel):
    added_count: int
    removed_count: int
    similarity_pct: float
    summary: str
    critical_changes: list[str]


def _extract_text_from_document(filename: str, content: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
        tmp_file.write(content)
        temp_path = tmp_file.name

    try:
        if suffix == ".docx":
            from docx import Document

            doc = Document(temp_path)
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        if suffix == ".txt":
            return read_text_file(temp_path)
    finally:
        Path(temp_path).unlink(missing_ok=True)

    raise HTTPException(status_code=400, detail="Supported formats: DOCX, TXT")


def _build_diff_response(diff: dict) -> DiffResponse:
    return DiffResponse(
        added_count=len(diff.get("added", [])),
        removed_count=len(diff.get("removed", [])),
        similarity_pct=float(diff.get("similarity_pct", 0.0)),
        summary=document_diff.generate_diff_report(diff),
        critical_changes=list(diff.get("critical_changes", [])),
    )


def _extract_list_items(text: str) -> list[str]:
    items: list[str] = []
    for line in text.splitlines():
        normalized = line.strip().strip("-•")
        if normalized and normalized not in items:
            items.append(normalized)
    return items


@router.post(
    "/tender",
    response_model=TenderAnalysisResponse,
    summary="Анализ тендерного PDF",
    description=(
        "Извлекает текст из тендерного PDF и формирует список рисков, противоречий и рекомендацию."
    ),
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "file": {"type": "string", "format": "binary"},
                            "session_id": {"type": "string"},
                            "role": {"type": "string", "default": "tender_specialist"},
                        },
                        "required": ["file"],
                    },
                    "example": {
                        "session_id": "88f0ea7c-cfa2-4af7-a226-cf12f862eeb4",
                        "role": "tender_specialist",
                    },
                }
            },
        }
    },
)
async def analyze_tender(
    request: Request,
    file: UploadFile = File(...),
    payload: TenderAnalysisRequest = Depends(TenderAnalysisRequest.as_form),
):
    """Анализ тендерного PDF через pipeline Researcher→Analyst→LegalExpert→Verifier."""
    _ = request
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Supported format: PDF only")

    file_bytes = await file.read()
    if len(file_bytes) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="File size exceeds 20 MB limit")

    try:
        parsed = pdf_parser.parse(file_bytes=file_bytes, filename=file.filename)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"PDF parsing error: {exc}") from exc

    joined_text = "\n".join(parsed.text_chunks)
    normative_refs = pdf_parser.extract_normative_refs(joined_text)

    message = (
        f"Проанализируй тендерный документ: {parsed.filename}.\n"
        f"Текст:\n{joined_text}\n"
        f"Нормативные ссылки: {', '.join(normative_refs) if normative_refs else 'не найдены'}."
    )

    session_id = payload.session_id or str(uuid.uuid4())

    try:
        result = await asyncio.wait_for(
            orchestrator.process(
                message=message,
                session_id=session_id,
                role=payload.role,
                intent="analyze_tender",
                extra_state={"normative_refs": normative_refs},
            ),
            timeout=ANALYZE_TIMEOUT_SECONDS,
        )
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Processing timeout (120 seconds)") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"LLM processing error: {exc}") from exc

    state = result.get("state", {}) if isinstance(result, dict) else {}
    legal_review = str(state.get("legal_review", ""))
    verification = state.get("verification", {}) if isinstance(state, dict) else {}

    confidence_value = float(state.get("confidence", 0.0) or 0.0)
    recommendation = str(verification.get("recommendation") or "УТОЧНИТЬ")

    contradictions = state.get("contradictions", []) if isinstance(state, dict) else []
    legal_issues = state.get("legal_issues") or _extract_list_items(legal_review)

    return TenderAnalysisResponse(
        session_id=result.get("session_id", session_id),
        risks=list(state.get("risks", [])),
        contradictions=list(contradictions),
        legal_issues=list(legal_issues),
        normative_refs=list(normative_refs),
        confidence=confidence_value,
        recommendation=recommendation,
    )


@router.post(
    "/diff",
    response_model=DiffResponse,
    summary="Сравнение версий документа по session_id",
)
async def analyze_diff(payload: DiffRequest, request: Request):
    """Сравнить две версии документов, сохранённых в архиве по session_id."""
    _ = request
    docs_v1 = await orchestrator.session_memory.get_session_documents(payload.session_id_v1)
    docs_v2 = await orchestrator.session_memory.get_session_documents(payload.session_id_v2)

    if not docs_v1:
        raise HTTPException(status_code=404, detail="Documents not found for session_id_v1")
    if not docs_v2:
        raise HTTPException(status_code=404, detail="Documents not found for session_id_v2")

    doc_v1 = docs_v1[0]
    doc_v2 = docs_v2[0]
    bytes_v1 = doc_v1.get("docx_bytes")
    bytes_v2 = doc_v2.get("docx_bytes")
    if not isinstance(bytes_v1, bytes) or not isinstance(bytes_v2, bytes):
        raise HTTPException(
            status_code=400,
            detail="Session documents do not contain binary content",
        )

    text_v1 = _extract_text_from_document(str(doc_v1.get("filename") or "v1.docx"), bytes_v1)
    text_v2 = _extract_text_from_document(str(doc_v2.get("filename") or "v2.docx"), bytes_v2)

    diff = document_diff.compare_texts(text_v1=text_v1, text_v2=text_v2)
    return _build_diff_response(diff)


@router.post(
    "/diff/upload",
    response_model=DiffResponse,
    summary="Сравнение двух загруженных версий документа",
)
async def analyze_diff_upload(
    request: Request,
    file_v1: UploadFile = File(...),
    file_v2: UploadFile = File(...),
):
    """Загрузить две версии документов (DOCX/TXT) и получить diff."""
    _ = request
    if not file_v1.filename or not file_v2.filename:
        raise HTTPException(status_code=400, detail="Both files are required")

    if not file_v1.filename.lower().endswith((".docx", ".txt")):
        raise HTTPException(status_code=400, detail="file_v1 format must be DOCX or TXT")
    if not file_v2.filename.lower().endswith((".docx", ".txt")):
        raise HTTPException(status_code=400, detail="file_v2 format must be DOCX or TXT")

    bytes_v1 = await file_v1.read()
    bytes_v2 = await file_v2.read()

    if len(bytes_v1) > MAX_UPLOAD_SIZE_BYTES or len(bytes_v2) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="File size exceeds 20 MB limit")

    text_v1 = _extract_text_from_document(file_v1.filename, bytes_v1)
    text_v2 = _extract_text_from_document(file_v2.filename, bytes_v2)

    diff = document_diff.compare_texts(text_v1=text_v1, text_v2=text_v2)
    return _build_diff_response(diff)
