"""Generate endpoints — генерация документов."""

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from core.orchestrator import Orchestrator

router = APIRouter()
orchestrator = Orchestrator()

ALLOWED_UNITS = ["м³", "м²", "пог.м.", "шт.", "т", "кг"]


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


class LetterGenerateRequest(BaseModel):
    """Параметры генерации делового письма."""

    letter_type: str
    situation: str
    recipient: str | None = None
    references: list[str] | None = None


class GenerateResponse(BaseModel):
    """Результат генерации."""

    document_id: str
    status: str
    preview: str | None = None
    download_url: str | None = None
    agents_log: list[dict] = []


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
    document = state.get("docx_payload") or {"content": result.get("reply")}

    return TKResponse(
        session_id=result["session_id"],
        document=document,
        agents_used=result.get("agents_used", []),
        confidence=result.get("confidence"),
        sha256=result.get("sha256"),
    )


@router.post("/generate/letter", response_model=GenerateResponse)
async def generate_letter(request: LetterGenerateRequest):
    """Генерация делового письма."""
    return GenerateResponse(
        document_id="letter-draft-001",
        status="draft",
        preview="[Генерация писем в разработке]",
    )


@router.post("/generate/ks")
async def generate_ks():
    """Генерация КС-2/КС-3 (Фаза 4)."""
    return {"status": "not_implemented", "message": "КС-2/КС-3 запланирован на Фазу 4"}
