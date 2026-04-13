"""Generate endpoints — генерация документов."""

import asyncio
import re
import tempfile
import uuid
from enum import StrEnum
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

from core.orchestrator import Orchestrator
from core.pdf_parser import PDFParser

router = APIRouter()
orchestrator = Orchestrator()
session_memory = orchestrator.session_memory
pdf_parser = PDFParser()

ALLOWED_UNITS = ["м³", "м²", "пог.м.", "шт.", "т", "кг"]
MAX_UPLOAD_SIZE_BYTES = 20 * 1024 * 1024
ANALYZE_TIMEOUT_SECONDS = 120


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


class WorkItem(BaseModel):
    """Позиция работ для КС-2/КС-3."""

    name: str
    unit: str
    volume: float
    norm_hours: float
    price_per_unit: float


class KSRequest(BaseModel):
    """Запрос на генерацию КС-2/КС-3."""

    object_name: str
    contract_number: str
    period_from: str
    period_to: str
    work_items: list[WorkItem] = Field(min_length=1, max_length=50)
    role: str = "pto_engineer"
    session_id: str | None = None


class KSResponse(BaseModel):
    """Ответ на генерацию КС-2/КС-3."""

    session_id: str
    ks2: dict
    ks3: dict
    docx_bytes_key: str
    total_cost: float
    total_hours: float
    sha256: str | None


class LetterType(StrEnum):
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
async def generate_tk(payload: TKRequest, request: Request):
    """Генерация технологической карты (ТК) через orchestrator."""
    _ = request
    session_id = payload.session_id or str(uuid.uuid4())
    norms_text = ", ".join(payload.norms) if payload.norms else "не указаны"
    message = (
        "Сформируй технологическую карту на русском языке.\n"
        f"Вид работ: {payload.work_type}.\n"
        f"Наименование объекта: {payload.object_name}.\n"
        f"Объём работ: {payload.volume} {payload.unit}.\n"
        f"Нормативы: {norms_text}.\n"
        "Подготовь структурированный документ для последующего DOCX-форматирования."
    )

    try:
        result = await orchestrator.process(
            message=message,
            session_id=session_id,
            role=payload.role,
            intent="generate_tk",
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"LLM processing error: {exc}") from exc

    state = result.get("state", {}) if isinstance(result, dict) else {}
    docx_bytes = state.get("docx_bytes")
    verification = state.get("verification", {}) if isinstance(state, dict) else {}
    sha256 = (verification or {}).get("sha256")
    if isinstance(docx_bytes, bytes):
        await session_memory.save_document(
            session_id=session_id,
            doc_type="tk",
            filename=f"tk_{session_id}.docx",
            docx_bytes=docx_bytes,
            sha256=sha256,
        )

    document = (
        state.get("final_output") or state.get("docx_payload") or {"content": result.get("reply")}
    )

    return TKResponse(
        session_id=result["session_id"],
        document=document,
        agents_used=result.get("agents_used", []),
        confidence=result.get("confidence"),
        sha256=sha256,
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
async def generate_letter_v2(payload: LetterRequest, request: Request):
    """Генерация делового письма через orchestrator."""
    _ = request
    session_id = payload.session_id or str(uuid.uuid4())
    body_points_text = "; ".join(payload.body_points)
    contract_number = payload.contract_number or "не указан"
    message = (
        f"Тип: {payload.letter_type.value}. "
        f"Получатель: {payload.addressee}. "
        f"Тема: {payload.subject}. "
        f"Тезисы: {body_points_text}. "
        f"Договор: {contract_number}."
    )

    try:
        result = await orchestrator.process(
            message=message,
            session_id=session_id,
            role=payload.role,
            intent="generate_letter",
            include_legal_expert=payload.include_npa,
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


@router.post("/generate/ks", response_model=KSResponse)
async def generate_ks(payload: KSRequest, request: Request):
    """Генерация КС-2/КС-3 через orchestrator pipeline."""
    _ = request
    session_id = payload.session_id or str(uuid.uuid4())
    work_names = ", ".join(item.name for item in payload.work_items)
    message = (
        "Сформируй КС-2/КС-3 на русском языке. "
        f"Объект: {payload.object_name}. "
        f"Договор: {payload.contract_number}. "
        f"Период: {payload.period_from} — {payload.period_to}. "
        f"Наименования работ: {work_names}."
    )

    extra_state = {
        "object_name": payload.object_name,
        "contract_number": payload.contract_number,
        "period_from": payload.period_from,
        "period_to": payload.period_to,
        "calculation_params": {"work_items": [item.model_dump() for item in payload.work_items]},
        "context": (f"Подготовь описательную часть КС-2 для следующих работ: {work_names}."),
    }

    try:
        result = await orchestrator.process(
            message=message,
            session_id=session_id,
            role=payload.role,
            intent="generate_ks",
            extra_state=extra_state,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"LLM processing error: {exc}") from exc

    state = result.get("state", {}) if isinstance(result, dict) else {}
    ks2 = state.get("ks2_data", {})
    ks3 = state.get("ks3_data", {})
    total_cost = float(ks2.get("total_cost", 0.0))
    total_hours = float(ks2.get("total_hours", 0.0))

    docx_bytes = state.get("docx_bytes")
    docx_bytes_key = session_id
    verification = state.get("verification", {}) if isinstance(state, dict) else {}
    sha256 = (verification or {}).get("sha256")
    if isinstance(docx_bytes, bytes):
        await session_memory.save_document(
            session_id=docx_bytes_key,
            doc_type="ks",
            filename=f"ks_{docx_bytes_key}.docx",
            docx_bytes=docx_bytes,
            sha256=sha256,
        )

    return KSResponse(
        session_id=result["session_id"],
        ks2=ks2,
        ks3=ks3,
        docx_bytes_key=docx_bytes_key,
        total_cost=total_cost,
        total_hours=total_hours,
        sha256=sha256,
    )


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
    request: Request,
    file: UploadFile = File(...),
    role: str = Form("tender_specialist"),
    session_id: str | None = Form(None),
):
    """Анализ загруженного PDF-документа через orchestrator."""
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

    normative_refs = pdf_parser.extract_normative_refs("\n".join(parsed.text_chunks))
    document_intent = (
        "analyze_tender" if _is_tender_document(parsed.filename, parsed.text_chunks) else "chat"
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
    except TimeoutError as exc:
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
async def download_tk_docx(session_id: str, request: Request):
    """Скачать ранее сгенерированный DOCX по session_id."""
    _ = request
    documents = await session_memory.get_session_documents(session_id)
    tk_document = next((doc for doc in documents if doc.get("doc_type") == "tk"), None)
    docx_bytes = tk_document.get("docx_bytes") if tk_document else None
    if not docx_bytes:
        raise HTTPException(status_code=404, detail="DOCX not found for this session")

    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".docx")
    tmp_path = Path(tmp_file.name)
    with tmp_file:
        tmp_file.write(docx_bytes)

    return FileResponse(
        path=tmp_path,
        media_type=("application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        filename=tk_document.get("filename") if tk_document else f"tk_{session_id}.docx",
    )


@router.get("/generate/ks/{session_id}/download")
async def download_ks_docx(session_id: str, request: Request):
    """Скачать ранее сгенерированный DOCX КС-2/КС-3 по session_id."""
    _ = request
    documents = await session_memory.get_session_documents(session_id)
    ks_document = next((doc for doc in documents if doc.get("doc_type") == "ks"), None)
    docx_bytes = ks_document.get("docx_bytes") if ks_document else None
    if not docx_bytes:
        raise HTTPException(status_code=404, detail="DOCX not found for this session")

    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".docx")
    tmp_path = Path(tmp_file.name)
    with tmp_file:
        tmp_file.write(docx_bytes)

    return FileResponse(
        path=tmp_path,
        media_type=("application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        filename=ks_document.get("filename") if ks_document else f"ks_{session_id}.docx",
    )
