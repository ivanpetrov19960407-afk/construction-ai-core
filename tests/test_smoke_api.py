"""Smoke tests for all API routes to ensure no internal server errors."""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from unittest.mock import AsyncMock

import pytest
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient

from api.main import app
from config.settings import settings


@pytest.fixture(autouse=True)
def _smoke_env(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Use safe in-memory/runtime test settings for smoke run."""
    monkeypatch.setattr(settings, "sqlite_db_path", ":memory:")
    monkeypatch.setattr(settings, "api_keys", ["smoke-key"])
    monkeypatch.setattr(settings, "admin_api_keys", ["smoke-key"])
    monkeypatch.setattr(settings, "default_llm_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "smoke-openai-key")

    # Redis/Qdrant mocks for routes that can touch cache/vector infra.
    monkeypatch.setattr("core.cache.RedisCache.get", AsyncMock(return_value=None))
    monkeypatch.setattr("core.cache.RedisCache.set", AsyncMock(return_value=None))
    monkeypatch.setattr("core.cache.RedisCache.delete", AsyncMock(return_value=None))
    monkeypatch.setattr("core.cache.RedisCache.enqueue", AsyncMock(return_value=True))
    monkeypatch.setattr("core.cache.RedisCache.dequeue", AsyncMock(return_value=None))
    monkeypatch.setattr("api.routes.generate.onec_exporter.export_ks2_to_xml", AsyncMock(return_value=b"<xml />"))
    monkeypatch.setattr("api.routes.generate.onec_exporter.export_m29_to_xml", AsyncMock(return_value=b"<xml />"))
    monkeypatch.setattr("api.routes.sign._fetch_exec_doc_for_verify", lambda *args, **kwargs: None)
    app.state.telegram_bot = None
    app.state.telegram_dp = None
    yield


def _route_path_with_params(path: str) -> str:
    replacements = {
        "{session_id}": "smoke-session",
        "{project_id}": "smoke-project",
        "{doc_id}": "1",
        "{id}": "1",
        "{token}": "smoke-token",
    }
    resolved = path
    for key, value in replacements.items():
        resolved = resolved.replace(key, value)

    while "{" in resolved and "}" in resolved:
        start = resolved.index("{")
        end = resolved.index("}", start)
        resolved = f"{resolved[:start]}smoke{resolved[end + 1:]}"
    return resolved


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_all_routes_no_500(method: str) -> None:
    """All GET/POST routes should respond with non-500 status in smoke mode."""

    async def _run() -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for route in app.routes:
                if not isinstance(route, APIRoute):
                    continue
                if method not in route.methods:
                    continue
                if route.path.startswith("/openapi") or route.path.startswith("/docs"):
                    continue

                url = _route_path_with_params(route.path)
                headers = {"X-API-Key": "smoke-key"}

                if method == "GET":
                    response = await client.get(url, headers=headers)
                else:
                    response = await client.post(url, json={}, headers=headers)

                assert response.status_code != 500, f"{method} {route.path} => {response.status_code}"

    asyncio.run(_run())
