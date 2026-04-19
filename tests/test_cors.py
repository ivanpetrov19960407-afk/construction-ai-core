"""Smoke tests CORS preflight for key /api/* routes."""

import asyncio

from httpx import ASGITransport, AsyncClient

from api.main import app

ALLOWED_ORIGIN = "tauri://localhost"
DISALLOWED_ORIGIN = "https://evil.example"


def test_preflight_allows_configured_tauri_origin_for_api_routes():
    """OPTIONS должен проходить для origin из CORS_ORIGINS."""

    async def _run() -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for path in ("/api/generate/letter", "/api/chat", "/api/rag/chat-upload"):
                response = await client.options(
                    path,
                    headers={
                        "Origin": ALLOWED_ORIGIN,
                        "Access-Control-Request-Method": "POST",
                        "Access-Control-Request-Headers": "content-type,x-api-key",
                    },
                )
                assert response.status_code == 200
                assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
                assert response.headers["access-control-allow-credentials"] == "true"

    asyncio.run(_run())


def test_preflight_rejects_origin_not_in_allow_list():
    """OPTIONS должен отклоняться для origin не из CORS_ORIGINS."""

    async def _run() -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.options(
                "/api/generate/letter",
                headers={
                    "Origin": DISALLOWED_ORIGIN,
                    "Access-Control-Request-Method": "POST",
                },
            )

        assert response.status_code in {400, 403}

    asyncio.run(_run())
