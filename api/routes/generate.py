"""Generate endpoints — генерация документов."""

import asyncio
import re
import tempfile
import uuid
from enum import Enum
from pathlib import Path
from typing import Literal

import structlog
from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

from agents.calculator import CalculatorAgent
from config.settings import settings
from core.cache import RedisCache
from core.llm_router import LLMRouter
from core.orchestrator import Orchestrator
from core.pdf_exporter import PDFExporter
from core.pdf_parser import PDFParser

router = APIRouter()
orchestrator = Orchestrator()
session_memory = orchestrator.session_memory
pdf_parser = PDFParser()
pdf_exporter = PDFExporter()
redis_cache = RedisCache(settings.redis_url)
logger = structlog.get_logger("api.generate")

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

class EstimateWorkItem(BaseModel):
    """Позиция работ для сметного расчёта по ГЭСН/ТСН."""

    work_type: str
    volume: float
    unit: str


class EstimateRequest(BaseModel):
    """Запрос на сметный расчёт по расценкам."""

    work_items: list[EstimateWorkItem] = Field(min_length=1, max_length=100)
    region: str = "Москва"


class EstimateResponse(BaseModel):
    """Ответ сметного расчёта."""

    items: list[dict]
    total_cost: float
    total_labor_hours: float
    region: str
    indexed_total_cost: float
    docx_available: bool = False


class LetterType(str, Enum):  # noqa: UP042
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


class PPRRequest(BaseModel):
    """Запрос на генерацию ППР."""

    work_type: str
    object_name: str
    developer: str = "ИИ-помощник Construction AI"
    start_date: str
    duration_days: int = Field(gt=0)
    workers_count: int = Field(gt=0)
    role: str = "pto_engineer"
    session_id: str | None = None
    export_format: Literal["docx", "pdf"] = "docx"
    norms: list[str] = []


@router.post(
    "/generate/tk",
    response_model=TKResponse,
    summary="Генерация технологической карты",
    description="Генерирует ТК на основе вида работ, объёмов и нормативов.",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "example": {
                        "work_type": "Устройство монолитной плиты",
                        "object_name": "ЖК Северный квартал, корпус 3",
                        "volume": 120.5,
                        "unit": "м³",
                        "norms": ["СП 70.13330", "СП 48.13330"],
                        "role": "pto_engineer",
                        "session_id": "1c53f75f-4036-4b8f-9046-a46ad9175d1f",
                    }
                }
            },
        }
    },
)
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
            extra_state={
                "work_type": payload.work_type,
                "object_name": payload.object_name,
                "volume": payload.volume,
                "unit": payload.unit,
                "norms": payload.norms,
                "tk_generator_input": {
                    "work_type": payload.work_type,
                    "object_name": payload.object_name,
                    "volume": payload.volume,
                    "unit": payload.unit,
                    "norms": payload.norms,
                },
            },
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
    tk_bridge_result = result.get("tk_bridge_result") if isinstance(result, dict) else None
    if isinstance(document, dict) and tk_bridge_result:
        document["tk_generator"] = tk_bridge_result

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


@router.post(
    "/generate/letter",
    response_model=LetterResponse,
    summary="Генерация делового письма",
    description="Формирует деловое письмо по заданному типу, адресату, теме и ключевым тезисам.",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "example": {
                        "letter_type": "запрос",
                        "addressee": "ООО СтройМонтаж",
                        "subject": "Предоставление исполнительной документации",
                        "body_points": [
                            "Просим направить акты скрытых работ",
                            "Указать сроки предоставления",
                        ],
                        "contract_number": "Д-17/2026",
                        "include_npa": True,
                        "role": "foreman",
                        "session_id": "802d28ad-2381-4837-97d6-4096bb5659fd",
                    }
                }
            },
        }
    },
)
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
    verification = state.get("verification", {}) if isinstance(state, dict) else {}
    sha256 = (verification or {}).get("sha256")
    docx_bytes = state.get("docx_bytes")
    if isinstance(docx_bytes, bytes):
        await session_memory.save_document(
            session_id=session_id,
            doc_type="letter",
            filename=f"letter_{session_id}.docx",
            docx_bytes=docx_bytes,
            sha256=sha256,
        )

    return LetterResponse(
        session_id=result["session_id"],
        document=document,
        agents_used=result.get("agents_used", []),
        legal_references=legal_references,
        confidence=result.get("confidence"),
    )


@router.post(
    "/generate/ppr",
    summary="Генерация ППР",
    description=(
        "Формирует проект производства работ (ППР) с возможностью дальнейшей выгрузки в DOCX/PDF."
    ),
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "example": {
                        "work_type": "Монтаж металлоконструкций",
                        "object_name": "Складской комплекс А-12",
                        "developer": "ПТО ООО Генподряд",
                        "start_date": "2026-05-10",
                        "duration_days": 45,
                        "workers_count": 18,
                        "role": "pto_engineer",
                        "session_id": "ea8f6325-26a2-4bd1-a831-c4b8ec3c5aa5",
                        "export_format": "docx",
                    }
                }
            },
        }
    },
)
async def generate_ppr(payload: PPRRequest, request: Request):
    """Генерация ППР в DOCX/PDF."""
    _ = request
    session_id = payload.session_id or str(uuid.uuid4())
    message = (
        "Сформируй проект производства работ (ППР) на русском языке. "
        f"Вид работ: {payload.work_type}. "
        f"Объект: {payload.object_name}. "
        f"Дата начала: {payload.start_date}. "
        f"Длительность: {payload.duration_days} дней. "
        f"Численность: {payload.workers_count} чел."
    )
    if len(payload.norms) > 5:
        queued = await redis_cache.enqueue(
            "doc_generation",
            {
                "task_type": "generate_ppr",
                "session_id": session_id,
                "payload": payload.model_dump(),
            },
        )
        if not queued:
            logger.warning(
                "ppr_enqueue_failed",
                session_id=session_id,
                queue="doc_generation",
            )
            raise HTTPException(
                status_code=503,
                detail="Task queue is unavailable. Please retry later.",
            )

        return {
            "session_id": session_id,
            "status": "queued",
            "queue": "doc_generation",
            "message": "Тяжелая генерация ППР поставлена в очередь.",
        }

    context = {
        "work_type": payload.work_type,
        "object_name": payload.object_name,
        "general_data": (
            f"Объект {payload.object_name}. Начало работ: {payload.start_date}. "
            "Продолжительность: "
            f"{payload.duration_days} дней. "
            f"Состав звена: {payload.workers_count} чел."
        ),
        "ppr_sections": [
            {"name": "Общие данные", "description": "Сведения об объекте и исходных данных"},
            {"name": "Календарный план", "description": "Очередность и сроки выполнения работ"},
            {"name": "Охрана труда", "description": "Меры безопасности и контроль рисков"},
        ],
        "site_plan_description": "Размещение временных зданий, складов и подъездных путей.",
        "schedule_table": [
            {
                "stage": "Подготовительный этап",
                "start_date": payload.start_date,
                "duration_days": 5,
            },
            {
                "stage": "Основные работы",
                "start_date": payload.start_date,
                "duration_days": payload.duration_days,
            },
        ],
        "safety_measures": [
            "Проведение вводного и целевого инструктажа.",
            "Применение СИЗ и ограждений опасных зон.",
            "Ежесменный контроль состояния техники.",
        ],
        "normative_docs": "СП 48.13330, СП 70.13330, ТК РФ ст. 214",
        "developer": payload.developer,
        "start_date": payload.start_date,
    }
    try:
        result = await orchestrator.process(
            message=message,
            session_id=session_id,
            role=payload.role,
            intent="generate_tk",
            extra_state={
                "template_name": "ppr_template",
                "template_context": context,
                "export_format": payload.export_format,
            },
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"LLM processing error: {exc}") from exc

    state = result.get("state", {}) if isinstance(result, dict) else {}
    docx_bytes = state.get("docx_bytes")
    if not isinstance(docx_bytes, bytes):
        raise HTTPException(status_code=500, detail="Generated DOCX is empty")
    await session_memory.save_document(
        session_id=session_id,
        doc_type="ppr",
        filename=f"ppr_{session_id}.docx",
        docx_bytes=docx_bytes,
        sha256=(state.get("verification", {}) or {}).get("sha256"),
    )

    return {
        "session_id": result["session_id"],
        "document": state.get("final_output", {}),
        "agents_used": result.get("agents_used", []),
        "confidence": result.get("confidence"),
    }


@router.post(
    "/generate/ks",
    response_model=KSResponse,
    summary="Генерация КС-2 и КС-3",
    description="Генерирует формы КС-2/КС-3 по перечню выполненных работ за указанный период.",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "example": {
                        "object_name": "БЦ Речной, секция Б",
                        "contract_number": "К-2026-11",
                        "period_from": "2026-03-01",
                        "period_to": "2026-03-31",
                        "work_items": [
                            {
                                "name": "Устройство бетонной подготовки",
                                "unit": "м³",
                                "volume": 80.0,
                                "norm_hours": 12.5,
                                "price_per_unit": 5200.0,
                            }
                        ],
                        "role": "pto_engineer",
                        "session_id": "7042f67a-7df6-4cf4-8fd4-065a2b3fac58",
                    }
                }
            },
        }
    },
)
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


@router.post(
    "/generate/estimate",
    response_model=EstimateResponse,
    summary="Сметный расчёт по ТСН/ГЭСН",
    description="Выполняет ориентировочный расчёт стоимости и трудозатрат по каталогу расценок.",
)
async def generate_estimate(payload: EstimateRequest):
    """Сметный калькулятор по справочнику расценок с региональным индексом."""
    calculator = CalculatorAgent(LLMRouter())
    estimate = calculator._calculate_estimate([item.model_dump() for item in payload.work_items])
    indexed_total_cost = calculator._apply_index(
        base_cost=float(estimate["total_cost"]),
        region=payload.region,
    )

    return EstimateResponse(
        items=estimate["items"],
        total_cost=float(estimate["total_cost"]),
        total_labor_hours=float(estimate["total_labor_hours"]),
        region=payload.region,
        indexed_total_cost=indexed_total_cost,
        docx_available=False,
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


@router.post(
    "/analyze/document",
    summary="Анализ загруженного документа",
    description=(
        "Анализирует PDF-документ и возвращает "
        "структурированный результат с рисками и рекомендациями."
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
                            "role": {"type": "string", "default": "tender_specialist"},
                            "session_id": {"type": "string"},
                        },
                        "required": ["file"],
                    },
                    "example": {
                        "role": "tender_specialist",
                        "session_id": "0b55b82d-d086-4f45-81d6-627dfd6d9fd7",
                    },
                }
            },
        }
    },
)
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
async def download_tk_docx(
    session_id: str,
    request: Request,
    format: Literal["docx", "pdf"] = Query(default="docx"),
):
    """Скачать ранее сгенерированный DOCX/PDF по session_id."""
    _ = request
    documents = await session_memory.get_session_documents(session_id)
    tk_document = next((doc for doc in documents if doc.get("doc_type") == "tk"), None)
    docx_bytes = tk_document.get("docx_bytes") if tk_document else None
    if not docx_bytes:
        raise HTTPException(status_code=404, detail="DOCX not found for this session")

    if format == "pdf":
        docx_bytes = pdf_exporter.docx_to_pdf(docx_bytes, f"tk_{session_id}.docx")
    suffix = ".pdf" if format == "pdf" else ".docx"
    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp_path = Path(tmp_file.name)
    with tmp_file:
        tmp_file.write(docx_bytes)

    return FileResponse(
        path=tmp_path,
        media_type=(
            "application/pdf"
            if format == "pdf"
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        filename=(
            f"tk_{session_id}.pdf"
            if format == "pdf"
            else (tk_document.get("filename") if tk_document else f"tk_{session_id}.docx")
        ),
    )


@router.get("/generate/ks/{session_id}/download")
async def download_ks_docx(
    session_id: str,
    request: Request,
    format: Literal["docx", "pdf"] = Query(default="docx"),
):
    """Скачать ранее сгенерированный DOCX/PDF КС-2/КС-3 по session_id."""
    _ = request
    documents = await session_memory.get_session_documents(session_id)
    ks_document = next((doc for doc in documents if doc.get("doc_type") == "ks"), None)
    docx_bytes = ks_document.get("docx_bytes") if ks_document else None
    if not docx_bytes:
        raise HTTPException(status_code=404, detail="DOCX not found for this session")

    if format == "pdf":
        docx_bytes = pdf_exporter.docx_to_pdf(docx_bytes, f"ks_{session_id}.docx")
    suffix = ".pdf" if format == "pdf" else ".docx"
    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp_path = Path(tmp_file.name)
    with tmp_file:
        tmp_file.write(docx_bytes)

    return FileResponse(
        path=tmp_path,
        media_type=(
            "application/pdf"
            if format == "pdf"
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        filename=(
            f"ks_{session_id}.pdf"
            if format == "pdf"
            else (ks_document.get("filename") if ks_document else f"ks_{session_id}.docx")
        ),
    )


@router.get("/generate/letter/{session_id}/download")
async def download_letter_docx(
    session_id: str,
    request: Request,
    format: Literal["docx", "pdf"] = Query(default="docx"),
):
    """Скачать ранее сгенерированный DOCX/PDF письма по session_id."""
    _ = request
    documents = await session_memory.get_session_documents(session_id)
    letter_document = next((doc for doc in documents if doc.get("doc_type") == "letter"), None)
    docx_bytes = letter_document.get("docx_bytes") if letter_document else None
    if not docx_bytes:
        raise HTTPException(status_code=404, detail="DOCX not found for this session")

    if format == "pdf":
        docx_bytes = pdf_exporter.docx_to_pdf(docx_bytes, f"letter_{session_id}.docx")
    suffix = ".pdf" if format == "pdf" else ".docx"
    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp_path = Path(tmp_file.name)
    with tmp_file:
        tmp_file.write(docx_bytes)

    return FileResponse(
        path=tmp_path,
        media_type=(
            "application/pdf"
            if format == "pdf"
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        filename=(
            f"letter_{session_id}.pdf"
            if format == "pdf"
            else (
                letter_document.get("filename") if letter_document else f"letter_{session_id}.docx"
            )
        ),
    )


@router.get("/generate/ppr/{session_id}/download")
async def download_ppr_docx(
    session_id: str,
    request: Request,
    format: Literal["docx", "pdf"] = Query(default="docx"),
):
    """Скачать ранее сгенерированный DOCX/PDF ППР по session_id."""
    _ = request
    documents = await session_memory.get_session_documents(session_id)
    ppr_document = next((doc for doc in documents if doc.get("doc_type") == "ppr"), None)
    docx_bytes = ppr_document.get("docx_bytes") if ppr_document else None
    if not docx_bytes:
        raise HTTPException(status_code=404, detail="DOCX not found for this session")

    if format == "pdf":
        docx_bytes = pdf_exporter.docx_to_pdf(docx_bytes, f"ppr_{session_id}.docx")
    suffix = ".pdf" if format == "pdf" else ".docx"
    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp_path = Path(tmp_file.name)
    with tmp_file:
        tmp_file.write(docx_bytes)

    return FileResponse(
        path=tmp_path,
        media_type=(
            "application/pdf"
            if format == "pdf"
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        filename=(
            f"ppr_{session_id}.pdf"
            if format == "pdf"
            else (ppr_document.get("filename") if ppr_document else f"ppr_{session_id}.docx")
        ),
    )
