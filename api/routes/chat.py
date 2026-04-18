"""Chat endpoint — основной интерфейс общения с ИИ."""

import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from core.billing import require_quota
from core.orchestrator import Orchestrator

router = APIRouter()
orchestrator = Orchestrator()


class ChatRequest(BaseModel):
    """Входящее сообщение пользователя."""

    message: str
    session_id: str | None = None
    role: str = "pto_engineer"  # pto_engineer | foreman | tender_specialist | admin


class ChatResponse(BaseModel):
    """Ответ от оркестратора."""

    reply: str
    session_id: str
    agents_used: list[str] = []
    confidence: float | None = None
    conflict_rate: float | None = None


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Чат с ИИ-ассистентом",
    description="Обрабатывает сообщение пользователя через оркестратор агентов и возвращает ответ.",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "example": {
                        "message": "Составь краткий план производства работ по кирпичной кладке.",
                        "session_id": "bdb98f51-9eaa-4e5c-aa53-3a53fce4e19a",
                        "role": "pto_engineer",
                    }
                }
            },
        }
    },
)
async def chat(
    payload: ChatRequest,
    request: Request,
    _quota: None = Depends(require_quota("ai_requests")),
):
    """Обработать сообщение пользователя через оркестратор."""
    _ = (request, _quota)
    session_id = payload.session_id or str(uuid.uuid4())
    result = await orchestrator.process(
        message=payload.message,
        session_id=session_id,
        role=payload.role,
    )
    return ChatResponse(
        reply=str(result.get("reply", "")),
        session_id=str(result.get("session_id", session_id)),
        agents_used=list(result.get("agents_used", [])),
        confidence=result.get("confidence"),
        conflict_rate=result.get("conflict_rate"),
    )
