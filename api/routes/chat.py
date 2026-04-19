"""Chat endpoint — основной интерфейс общения с ИИ."""

import json
import uuid
from hashlib import sha256

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
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
    message_id: str | None = None


class SourceItem(BaseModel):
    title: str
    page: int
    score: float


class ChatResponse(BaseModel):
    """Ответ от оркестратора."""

    reply: str
    session_id: str
    agents_used: list[str] = []
    confidence: float | None = None
    conflict_rate: float | None = None
    sources: list[SourceItem] = []
    message_id: str | None = None


def _sse_event(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _resolve_chat_user_id(request: Request) -> str:
    state_username = getattr(request.state, "username", None)
    if state_username:
        return str(state_username)

    api_key = request.headers.get("X-API-Key")
    if api_key:
        digest = sha256(api_key.encode("utf-8")).hexdigest()
        return f"api-key:{digest}"

    return "anonymous"


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
    stream: bool = Query(False, description="Вернуть ответ чата в формате SSE"),
    _quota: None = Depends(require_quota("ai_requests")),
):
    """Обработать сообщение пользователя через оркестратор."""
    _ = (request, _quota)
    session_id = payload.session_id or str(uuid.uuid4())
    result = await orchestrator.process(
        message=payload.message,
        session_id=session_id,
        role=payload.role,
        user_id=_resolve_chat_user_id(request),
    )

    if stream or "text/event-stream" in request.headers.get("Accept", ""):

        async def _stream():
            yield _sse_event("progress", {"stage": "retrieval", "progress": 35})
            for source in list(result.get("sources", [])):
                yield _sse_event("source", {"source": source})
            yield _sse_event(
                "done",
                {
                    "stage": "done",
                    "progress": 100,
                    "result": {
                        "reply": str(result.get("reply", "")),
                        "session_id": str(result.get("session_id", session_id)),
                        "agents_used": list(result.get("agents_used", [])),
                        "confidence": result.get("confidence"),
                        "conflict_rate": result.get("conflict_rate"),
                        "sources": list(result.get("sources", [])),
                        "message_id": payload.message_id,
                    },
                },
            )

        return StreamingResponse(_stream(), media_type="text/event-stream")

    return ChatResponse(
        reply=str(result.get("reply", "")),
        session_id=str(result.get("session_id", session_id)),
        agents_used=list(result.get("agents_used", [])),
        confidence=result.get("confidence"),
        conflict_rate=result.get("conflict_rate"),
        sources=list(result.get("sources", [])),
        message_id=payload.message_id,
    )
