"""Tests for billing plans and usage counters."""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from api.main import app
from config.settings import settings
from core.billing import PLAN_LIMITS, PlanTier, UsageCounter


class _MockRedis:
    def __init__(self):
        self.store: dict[str, str] = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None):
        _ = ex
        self.store[key] = value


class _MockRedisCache:
    def __init__(self):
        self._redis = _MockRedis()

    async def get(self, key: str) -> str | None:
        return await self._redis.get(key)

    async def set(self, key: str, value: str, ttl: int = 3600) -> None:
        await self._redis.set(key, value, ex=ttl)


def test_usage_counter_increment():
    counter = UsageCounter(_MockRedisCache())

    async def _run() -> None:
        first = await counter.increment("org-1", "ai_requests")
        second = await counter.increment("org-1", "ai_requests")
        usage = await counter.get_usage("org-1", "ai_requests")
        assert first == 1
        assert second == 2
        assert usage == 2

    asyncio.run(_run())


def test_enterprise_no_limit():
    counter = UsageCounter(_MockRedisCache())

    async def _run() -> None:
        for _ in range(100):
            await counter.increment("org-enterprise", "ai_requests")
        assert PLAN_LIMITS[PlanTier.ENTERPRISE]["ai_requests"] == -1
        allowed = await counter.check_limit("org-enterprise", "ai_requests", PlanTier.ENTERPRISE)
        assert allowed is True

    asyncio.run(_run())


def test_free_plan_limit_exceeded(monkeypatch):
    from api.routes import chat
    from core import billing

    old_api_keys = settings.api_keys
    settings.api_keys = ["billing-key"]

    counter = UsageCounter(_MockRedisCache())

    async def _pre_fill() -> None:
        for _ in range(PLAN_LIMITS[PlanTier.FREE]["ai_requests"]):
            await counter.increment("default", "ai_requests")

    asyncio.run(_pre_fill())

    monkeypatch.setattr(billing, "usage_counter", counter)
    monkeypatch.setattr(chat, "usage_counter", counter, raising=False)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/chat",
                json={"message": "test"},
                headers={"X-API-Key": "billing-key"},
            )
    finally:
        settings.api_keys = old_api_keys

    assert response.status_code == 429
    assert "Quota exceeded" in response.json()["detail"]
