"""Telegram/Desktop linking and notifications API."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.session_bridge import (
    InvalidTelegramLinkTokenError,
    fetch_and_mark_notifications,
    parse_telegram_link_token,
    upsert_telegram_link,
)

router = APIRouter(prefix="/link", tags=["linking"])
notifications_router = APIRouter(prefix="/notifications", tags=["notifications"])


class TelegramLinkRequest(BaseModel):
    code: str = Field(min_length=16)
    user_id: str = Field(min_length=1, max_length=255)
    session_id: str = Field(min_length=1, max_length=255)


class TelegramLinkResponse(BaseModel):
    ok: bool
    telegram_user_id: str
    user_id: str
    session_id: str


class NotificationsResponse(BaseModel):
    notifications: list[dict[str, str]]


@router.post("/telegram", response_model=TelegramLinkResponse)
async def link_telegram(payload: TelegramLinkRequest) -> TelegramLinkResponse:
    """Bind telegram user with desktop user/session using bot-issued code."""
    try:
        telegram_user_id, _bot_session_id = parse_telegram_link_token(payload.code)
    except InvalidTelegramLinkTokenError as exc:
        raise HTTPException(status_code=400, detail="invalid telegram link code") from exc

    await upsert_telegram_link(
        telegram_user_id=telegram_user_id,
        user_id=payload.user_id,
        session_id=payload.session_id,
    )
    return TelegramLinkResponse(
        ok=True,
        telegram_user_id=telegram_user_id,
        user_id=payload.user_id,
        session_id=payload.session_id,
    )


@notifications_router.get("", response_model=NotificationsResponse)
async def get_notifications(user_id: str, limit: int = 20) -> NotificationsResponse:
    """Return unread notifications for desktop polling."""
    normalized_limit = min(max(limit, 1), 100)
    notifications = await fetch_and_mark_notifications(user_id=user_id, limit=normalized_limit)
    return NotificationsResponse(notifications=notifications)
