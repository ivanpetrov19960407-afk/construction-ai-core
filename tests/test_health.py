"""Тесты health-check endpoint."""

import asyncio

from httpx import ASGITransport, AsyncClient

from api.main import app


def test_health_check():
    """GET /health должен возвращать status ok."""

    async def _run() -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "construction-ai-core"

    asyncio.run(_run())


def test_health_has_version():
    """Health-check должен содержать версию."""

    async def _run() -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")
        data = response.json()
        assert "version" in data

    asyncio.run(_run())
