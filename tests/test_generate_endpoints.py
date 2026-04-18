"""Интеграционные проверки generate-эндпоинтов и скачивания DOCX."""

import asyncio
from unittest.mock import AsyncMock

from httpx import ASGITransport, AsyncClient

from api.main import app
from api.routes import generate
from config.settings import settings


def test_tk_generate_and_download():
    """POST /api/generate/tk должен вернуть session_id и обеспечить DOCX-download."""

    async def _run() -> None:
        old_keys = settings.api_keys
        settings.api_keys = ["valid-key"]
        generate.SESSION_STORE.clear()
        mocked_process = AsyncMock(
            return_value={
                "session_id": "tk-session-1",
                "agents_used": ["researcher", "author", "critic", "verifier", "formatter"],
                "confidence": 0.91,
                "reply": "Текст сгенерированной технологической карты",
                "state": {"docx_payload": {"title": "ТК", "sections": []}},
            }
        )
        generate.orchestrator.process = mocked_process

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/generate/tk",
                    json={
                        "work_type": "бетонирование монолитных конструкций",
                        "object_name": "ЖК Север",
                        "volume": 55.0,
                        "unit": "м³",
                        "norms": ["СП 70.13330"],
                        "role": "pto_engineer",
                        "session_id": "tk-session-1",
                    },
                    headers={"X-API-Key": "valid-key"},
                )
                assert response.status_code == 200
                payload = response.json()
                assert payload["session_id"] == "tk-session-1"
                assert isinstance(payload["result"], str)

                download_response = await client.get(
                    "/api/generate/tk/tk-session-1/download",
                    headers={"X-API-Key": "valid-key"},
                )
        finally:
            settings.api_keys = old_keys

        assert download_response.status_code == 200
        assert (
            download_response.headers["content-type"]
            == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        assert download_response.content

    asyncio.run(_run())
