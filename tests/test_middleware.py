"""Tests for API key middleware behavior."""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app
from config.settings import settings


def test_request_without_api_key_returns_401():
    """Protected endpoint should reject requests without X-API-Key."""

    async def _run() -> None:
        old_keys = settings.api_keys
        settings.api_keys = ["valid-key"]
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post("/api/chat", json={"message": "ping"})
        finally:
            settings.api_keys = old_keys

        assert response.status_code == 401
        assert response.json() == {"detail": "Invalid API key"}

    asyncio.run(_run())


def test_request_with_valid_api_key_returns_200(monkeypatch: pytest.MonkeyPatch):
    """Protected endpoint should pass with a valid API key."""

    async def _run() -> None:
        old_keys = settings.api_keys
        settings.api_keys = ["valid-key"]

        async def _fake_process(message: str, session_id: str, role: str):
            return {
                "reply": f"echo: {message}",
                "session_id": session_id,
                "agents_used": ["mock"],
                "confidence": 1.0,
            }

        monkeypatch.setattr("api.routes.chat.orchestrator.process", _fake_process)

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/chat",
                    json={"message": "ping"},
                    headers={"X-API-Key": "valid-key"},
                )
        finally:
            settings.api_keys = old_keys

        assert response.status_code == 200
        data = response.json()
        assert data["reply"] == "echo: ping"
        assert data["agents_used"] == ["mock"]

    asyncio.run(_run())


def test_health_is_accessible_without_api_key():
    """Health endpoint should be excluded from API key check."""

    async def _run() -> None:
        old_keys = settings.api_keys
        settings.api_keys = ["valid-key"]
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/health")
        finally:
            settings.api_keys = old_keys

        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    asyncio.run(_run())


def test_cors_preflight_with_api_key_header_is_allowed():
    """Browser preflight requests should pass before API key validation."""

    async def _run() -> None:
        old_keys = settings.api_keys
        settings.api_keys = ["valid-key"]
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.options(
                    "/api/billing/plan",
                    headers={
                        "Origin": "http://localhost:1420",
                        "Access-Control-Request-Method": "GET",
                        "Access-Control-Request-Headers": "x-api-key",
                    },
                )
        finally:
            settings.api_keys = old_keys

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "http://localhost:1420"
        assert "x-api-key" in response.headers["access-control-allow-headers"].lower()

    asyncio.run(_run())
