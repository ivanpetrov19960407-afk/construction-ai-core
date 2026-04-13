"""Chat endpoint — основной интерфейс общения с ИИ."""

import uuid

from fastapi import APIRouter
from pydantic import BaseModel

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


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Обработать сообщение пользователя через оркестратор."""
    session_id = request.session_id or str(uuid.uuid4())
    result = await orchestrator.process(
        message=request.message,
        session_id=session_id,
        role=request.role,
    )
    return result
