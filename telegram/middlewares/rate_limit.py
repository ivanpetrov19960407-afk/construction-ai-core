"""Rate limit middleware for Telegram handlers."""

from __future__ import annotations

import importlib
import importlib.util
import math
from typing import Any

from aiogram import BaseMiddleware

from config.settings import settings

RATE_LIMIT_MAX = 10
RATE_LIMIT_WINDOW_SECONDS = 60


class TelegramRateLimitMiddleware(BaseMiddleware):
    """Enforces 10 req/min per chat_id."""

    async def __call__(self, handler, event, data):  # type: ignore[override]
        chat = getattr(event, "chat", None)
        if chat is None:
            return await handler(event, data)

        allowed, retry_after = await check_rate_limit(int(chat.id))
        if not allowed:
            message = getattr(event, "answer", None)
            if callable(message):
                await event.answer(f"Слишком часто, попробуйте через {retry_after} сек")
            return None
        return await handler(event, data)


def _redis_client() -> Any | None:
    if importlib.util.find_spec("redis") is None:
        return None
    redis_asyncio = importlib.import_module("redis.asyncio")
    return redis_asyncio.Redis.from_url(settings.redis_url, decode_responses=True)


async def check_rate_limit(chat_id: int) -> tuple[bool, int]:
    """Return (is_allowed, retry_after_seconds)."""
    key = f"tg:rate_limit:{chat_id}"
    client = _redis_client()
    if client is None:
        return True, 0

    try:
        count = await client.incr(key)
        if count == 1:
            await client.expire(key, RATE_LIMIT_WINDOW_SECONDS)
        if count <= RATE_LIMIT_MAX:
            return True, 0
        ttl = await client.ttl(key)
        retry_after = max(
            1,
            math.ceil(float(ttl if ttl and ttl > 0 else RATE_LIMIT_WINDOW_SECONDS)),
        )
        return False, retry_after
    finally:
        await client.close()
