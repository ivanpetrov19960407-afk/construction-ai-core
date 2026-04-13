"""Generate endpoints — генерация документов."""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


# ── Схемы запросов ─────────────────────────────


class TKGenerateRequest(BaseModel):
    """Параметры генерации технологической карты."""

    work_type: str  # монолит / кладка / кровля / и т.д.
    volume: str | None = None  # объём работ
    deadline: str | None = None  # срок выполнения
    brigade_size: int | None = None  # размер бригады
    conditions: str | None = None  # особые условия
    rd_file_path: str | None = None  # путь к загруженной РД


class LetterGenerateRequest(BaseModel):
    """Параметры генерации делового письма."""

    letter_type: str  # запрос | ответ | претензия | уведомление
    situation: str  # описание ситуации
    recipient: str | None = None  # получатель
    references: list[str] | None = None  # ссылки на документы


class GenerateResponse(BaseModel):
    """Результат генерации."""

    document_id: str
    status: str  # draft | review | approved
    preview: str | None = None
    download_url: str | None = None
    agents_log: list[dict] = []


# ── Endpoints ──────────────────────────────────


@router.post("/generate/tk", response_model=GenerateResponse)
async def generate_tk(request: TKGenerateRequest):
    """Генерация технологической карты (ТК)."""
    # TODO: Фаза 1 — вызов tk-generator через subprocess
    # TODO: Фаза 2 — полноценная генерация через оркестратор
    return GenerateResponse(
        document_id="tk-draft-001",
        status="draft",
        preview="[Генерация ТК в разработке]",
    )


@router.post("/generate/letter", response_model=GenerateResponse)
async def generate_letter(request: LetterGenerateRequest):
    """Генерация делового письма."""
    # TODO: Фаза 2 — генератор писем через оркестратор
    return GenerateResponse(
        document_id="letter-draft-001",
        status="draft",
        preview="[Генерация писем в разработке]",
    )


@router.post("/generate/ks")
async def generate_ks():
    """Генерация КС-2/КС-3 (Фаза 4)."""
    return {"status": "not_implemented", "message": "КС-2/КС-3 запланирован на Фазу 4"}
