"""Telegram auth middleware: attaches user API key from Redis."""

from __future__ import annotations

import importlib
import importlib.util
from typing import Any

from aiogram import BaseMiddleware

from config.settings import settings

USER_API_KEY_TTL_SECONDS = 90 * 24 * 60 * 60


class TelegramAuthMiddleware(BaseMiddleware):
    """Inject chat-scoped api_key into handler data."""

    async def __call__(self, handler, event, data):  # type: ignore[override]
        chat = getattr(event, "chat", None)
        if chat is None:
            return await handler(event, data)

        api_key = await get_api_key_for_chat(int(chat.id))
        if api_key:
            data["api_key"] = api_key
        return await handler(event, data)


def _redis_client() -> Any | None:
    if importlib.util.find_spec("redis") is None:
        return None
    redis_asyncio = importlib.import_module("redis.asyncio")
    return redis_asyncio.Redis.from_url(settings.redis_url, decode_responses=True)


async def get_api_key_for_chat(chat_id: int) -> str:
    """Resolve chat api key from Redis or fallback to static API key."""
    key_name = f"tg:user:{chat_id}:api_key"
    client = _redis_client()
    if client is not None:
        try:
            value = await client.get(key_name)
            if value:
                return str(value)
        finally:
            await client.close()
    if settings.api_keys:
        return settings.api_keys[0]
    return ""


async def save_api_key_for_chat(chat_id: int, api_key: str) -> None:
    """Persist chat api key with 90-day TTL."""
    client = _redis_client()
    if client is None:
        return
    try:
        await client.set(f"tg:user:{chat_id}:api_key", api_key, ex=USER_API_KEY_TTL_SECONDS)
    finally:
        await client.close()


async def delete_api_key_for_chat(chat_id: int) -> None:
    client = _redis_client()
    if client is None:
        return
    try:
        await client.delete(f"tg:user:{chat_id}:api_key")
    finally:
        await client.close()
