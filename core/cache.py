"""Redis cache и простая Redis-очередь задач."""

from __future__ import annotations

import importlib
import importlib.util
import json
from collections.abc import Awaitable, Callable
from typing import Any

import structlog


class RedisCache:
    """Async-обёртка над Redis с graceful fallback."""

    def __init__(self, url: str = "redis://redis:6379"):
        self.url = url
        self._logger = structlog.get_logger("core.cache")
        self._redis: Any | None = None

        if importlib.util.find_spec("redis") is None:
            self._logger.warning("redis_module_unavailable", url=url)
            return

        redis_asyncio = importlib.import_module("redis.asyncio")
        self._redis = redis_asyncio.Redis.from_url(url, decode_responses=True)

    async def get(self, key: str) -> str | None:
        """Получить значение по ключу."""
        if self._redis is None:
            return None
        try:
            return await self._redis.get(key)
        except Exception as exc:  # noqa: BLE001
            self._logger.warning("redis_get_failed", key=key, error=str(exc))
            return None

    async def set(self, key: str, value: str, ttl: int = 3600) -> None:
        """Установить значение с TTL."""
        if self._redis is None:
            return
        try:
            await self._redis.set(key, value, ex=ttl)
        except Exception as exc:  # noqa: BLE001
            self._logger.warning("redis_set_failed", key=key, error=str(exc))

    async def delete(self, key: str) -> None:
        """Удалить ключ."""
        if self._redis is None:
            return
        try:
            await self._redis.delete(key)
        except Exception as exc:  # noqa: BLE001
            self._logger.warning("redis_delete_failed", key=key, error=str(exc))

    async def get_or_compute(
        self,
        key: str,
        compute_fn: Callable[[], Awaitable[str]],
        ttl: int = 3600,
    ) -> str:
        """Вернуть кэш или вычислить, сохранить и вернуть."""
        cached = await self.get(key)
        if cached is not None:
            return cached

        value = await compute_fn()
        await self.set(key, value, ttl=ttl)
        return value

    async def enqueue(self, queue: str, task: dict[str, Any]) -> None:
        """Добавить задачу в Redis-очередь."""
        if self._redis is None:
            return
        try:
            await self._redis.rpush(queue, json.dumps(task, ensure_ascii=False))
        except Exception as exc:  # noqa: BLE001
            self._logger.warning("redis_enqueue_failed", queue=queue, error=str(exc))

    async def dequeue(self, queue: str) -> dict[str, Any] | None:
        """Извлечь задачу из Redis-очереди (FIFO)."""
        if self._redis is None:
            return None
        try:
            item = await self._redis.lpop(queue)
        except Exception as exc:  # noqa: BLE001
            self._logger.warning("redis_dequeue_failed", queue=queue, error=str(exc))
            return None

        if item is None:
            return None

        try:
            return json.loads(item)
        except json.JSONDecodeError:
            self._logger.warning("redis_queue_item_invalid", queue=queue)
            return None
