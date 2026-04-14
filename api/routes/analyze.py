"""Analyze endpoints — анализ тендерной документации."""

from __future__ import annotations

import asyncio
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from core.orchestrator import Orchestrator
from core.pdf_parser import PDFParser

router = APIRouter()
orchestrator = Orchestrator()
pdf_parser = PDFParser()

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
