"""Chat endpoint — основной интерфейс общения с ИИ."""

from fastapi import APIRouter
from pydantic import BaseModel

from core.orchestrator import Orchestrator

router = APIRouter()


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
    orchestrator = Orchestrator()
    result = await orchestrator.process(
        message=request.message,
        session_id=request.session_id,
        role=request.role,
    )
    return result
