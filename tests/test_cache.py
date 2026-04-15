"""Тесты RedisCache."""

import asyncio

from core.cache import RedisCache


class _MockRedis:
    def __init__(self):
        self.store: dict[str, str] = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None):
        _ = ex
        self.store[key] = value

    async def delete(self, key: str):
        self.store.pop(key, None)


def test_cache_set_and_get():
    cache = RedisCache()
    cache._redis = _MockRedis()  # type: ignore[assignment]

    asyncio.run(cache.set("foo", "bar", ttl=60))
    value = asyncio.run(cache.get("foo"))

    assert value == "bar"


def test_cache_fallback_on_unavailable():
    cache = RedisCache()

    class _UnavailableRedis:
        async def get(self, key: str):
            raise OSError("redis down")

        async def set(self, key: str, value: str, ex: int | None = None):
            _ = (key, value, ex)
            raise OSError("redis down")

        async def delete(self, key: str):
            _ = key
            raise OSError("redis down")

    cache._redis = _UnavailableRedis()  # type: ignore[assignment]

    async def _compute() -> str:
        return "computed"

    value = asyncio.run(cache.get_or_compute("key", _compute, ttl=60))

    assert value == "computed"
    assert asyncio.run(cache.get("key")) is None
    assert asyncio.run(cache.enqueue("doc_generation", {"task": 1})) is False
