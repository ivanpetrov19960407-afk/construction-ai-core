"""Generate endpoints — генерация документов."""

import asyncio
import re
import tempfile
import uuid
from enum import Enum
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

from core.orchestrator import Orchestrator
from core.pdf_parser import PDFParser

router = APIRouter()
orchestrator = Orchestrator()
pdf_parser = PDFParser()

ALLOWED_UNITS = ["м³", "м²", "пог.м.", "шт.", "т", "кг"]
MAX_UPLOAD_SIZE_BYTES = 20 * 1024 * 1024
ANALYZE_TIMEOUT_SECONDS = 120

DOCX_CACHE: dict[str, bytes] = {}


class TKRequest(BaseModel):
    """Запрос на генерацию технологической карты."""

    work_type: str = Field(min_length=5)
    object_name: str
    volume: float
    unit: str
    norms: list[str] = []
    role: str = "pto_engineer"
    session_id: str | None = None

    @field_validator("volume")
    @classmethod
    def validate_volume(cls, value: float) -> float:
        """Объём работ должен быть больше нуля."""
        if value <= 0:
            raise ValueError("volume must be > 0")
        return value

    @field_validator("unit")
    @classmethod
    def validate_unit(cls, value: str) -> str:
        """Единица измерения должна быть из разрешённого списка."""
        if value not in ALLOWED_UNITS:
            raise ValueError(f"unit must be one of: {', '.join(ALLOWED_UNITS)}")
        return value


class TKResponse(BaseModel):
    """Ответ на генерацию технологической карты."""

    session_id: str
    document: dict
    agents_used: list[str]
    confidence: float | None
    sha256: str | None


class LetterType(str, Enum):
    """Тип делового письма."""

    REQUEST = "запрос"
    CLAIM = "претензия"
    NOTIFICATION = "уведомление"
    RESPONSE = "ответ"


class LetterRequest(BaseModel):
    """Запрос на генерацию делового письма."""

    letter_type: LetterType
    addressee: str
    subject: str
    body_points: list[str] = Field(min_length=1, max_length=10)
    contract_number: str | None = None
    include_npa: bool = True
    role: str = "foreman"
    session_id: str | None = None


class LetterResponse(BaseModel):
    """Ответ на генерацию делового письма."""

    session_id: str
    document: dict
    agents_used: list[str]
    legal_references: list[str]
    confidence: float | None


@router.post("/generate/tk", response_model=TKResponse)
async def generate_tk(request: TKRequest):
    """Генерация технологической карты (ТК) через orchestrator."""
    session_id = request.session_id or str(uuid.uuid4())
    norms_text = ", ".join(request.norms) if request.norms else "не указаны"
    message = (
        "Сформируй технологическую карту на русском языке.\n"
        f"Вид работ: {request.work_type}.\n"
        f"Наименование объекта: {request.object_name}.\n"
        f"Объём работ: {request.volume} {request.unit}.\n"
        f"Нормативы: {norms_text}.\n"
        "Подготовь структурированный документ для последующего DOCX-форматирования."
    )

    try:
        result = await orchestrator.process(
            message=message,
            session_id=session_id,
            role=request.role,
            intent="generate_tk",
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"LLM processing error: {exc}") from exc

    state = result.get("state", {}) if isinstance(result, dict) else {}
    docx_bytes = state.get("docx_bytes")
    if isinstance(docx_bytes, bytes):
        DOCX_CACHE[session_id] = docx_bytes

    document = (
        state.get("final_output")
        or state.get("docx_payload")
        or {"content": result.get("reply")}
    )

    return TKResponse(
        session_id=result["session_id"],
        document=document,
        agents_used=result.get("agents_used", []),
        confidence=result.get("confidence"),
        sha256=result.get("sha256"),
    )


LEGAL_REFERENCE_PATTERN = re.compile(
    r"(ст\.\s*\d+(?:\.\d+)?\s*[А-ЯA-Zа-яa-zЁё\s]{0,25}РФ|ФЗ-\d+)",
    flags=re.IGNORECASE,
)


def _extract_legal_references(history: list[dict]) -> list[str]:
    """Извлечь ссылки на НПА из history записей Legal Expert."""
    references: list[str] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        agent_name = str(item.get("agent_name", "")).lower().replace(" ", "")
        if agent_name != "legalexpert":
            continue

        output = str(item.get("output", ""))
        matches = LEGAL_REFERENCE_PATTERN.findall(output)
        for match in matches:
            normalized = " ".join(match.strip().split())
            if normalized and normalized not in references:
                references.append(normalized)
    return references


@router.post("/generate/letter", response_model=LetterResponse)
async def generate_letter_v2(request: LetterRequest):
    """Генерация делового письма через orchestrator."""
    session_id = request.session_id or str(uuid.uuid4())
    body_points_text = "; ".join(request.body_points)
    contract_number = request.contract_number or "не указан"
    message = (
        f"Тип: {request.letter_type.value}. "
        f"Получатель: {request.addressee}. "
        f"Тема: {request.subject}. "
        f"Тезисы: {body_points_text}. "
        f"Договор: {contract_number}."
    )

    try:
        result = await orchestrator.process(
            message=message,
            session_id=session_id,
            role=request.role,
            intent="generate_letter",
            include_legal_expert=request.include_npa,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"LLM processing error: {exc}") from exc

    state = result.get("state", {}) if isinstance(result, dict) else {}
    history = state.get("history", []) if isinstance(state, dict) else []
    document = state.get("docx_payload") or {"content": result.get("reply")}
    legal_references = _extract_legal_references(history)

    return LetterResponse(
        session_id=result["session_id"],
        document=document,
        agents_used=result.get("agents_used", []),
        legal_references=legal_references,
        confidence=result.get("confidence"),
    )


@router.post("/generate/ks")
async def generate_ks():
    """Генерация КС-2/КС-3 (Фаза 4)."""
    return {"status": "not_implemented", "message": "КС-2/КС-3 запланирован на Фазу 4"}


def _is_tender_document(filename: str, text_chunks: list[str]) -> bool:
    """Определить, относится ли документ к тендерным."""
    indicators = ("тендер", "закупк", "конкурс", "аукцион", "44-фз", "223-фз")
    haystack = f"{filename} {' '.join(text_chunks[:4])}".lower()
    return any(indicator in haystack for indicator in indicators)


def _extract_risks(analysis: str) -> list[str]:
    """Выделить строки с рисками из итогового анализа."""
    risks: list[str] = []
    for line in analysis.splitlines():
        normalized = line.strip(" -•\t")
        if normalized and "риск" in normalized.lower():
            risks.append(normalized)
    return risks


@router.post("/analyze/document")
async def analyze_document(
    file: UploadFile = File(...),
    role: str = Form("tender_specialist"),
    session_id: str | None = Form(None),
):
    """Анализ загруженного PDF-документа через orchestrator."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Supported format: PDF only")

    file_bytes = await file.read()
    if len(file_bytes) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="File size exceeds 20 MB limit")

    try:
        parsed = pdf_parser.parse(file_bytes=file_bytes, filename=file.filename)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"PDF parsing error: {exc}") from exc

    normative_refs = pdf_parser.extract_normative_refs("\n".join(parsed.text_chunks))
    document_intent = (
        "analyze_tender"
        if _is_tender_document(parsed.filename, parsed.text_chunks)
        else "chat"
    )
    session_id = session_id or str(uuid.uuid4())
    message = (
        f"Проанализируй документ: {parsed.filename}.\n"
        f"Текстовые фрагменты:\n{chr(10).join(parsed.text_chunks)}\n"
        f"Нормативные ссылки: {', '.join(normative_refs) if normative_refs else 'не найдены'}."
    )

    try:
        result = await asyncio.wait_for(
            orchestrator.process(
                message=message,
                session_id=session_id,
                role=role,
                intent=document_intent,
            ),
            timeout=ANALYZE_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Processing timeout (120 seconds)") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"LLM processing error: {exc}") from exc

    analysis = str(result.get("reply") or "")
    return {
        "analysis": analysis,
        "normative_refs": normative_refs,
        "risks": _extract_risks(analysis),
        "session_id": result.get("session_id", session_id),
    }


@router.get("/generate/tk/{session_id}/download")
async def download_tk_docx(session_id: str):
    """Скачать ранее сгенерированный DOCX по session_id."""
    docx_bytes = DOCX_CACHE.get(session_id)
    if not docx_bytes:
        raise HTTPException(status_code=404, detail="DOCX not found for this session")

    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".docx")
    tmp_path = Path(tmp_file.name)
    with tmp_file:
        tmp_file.write(docx_bytes)

    return FileResponse(
        path=tmp_path,
        media_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        filename=f"tk_{session_id}.docx",
    )
