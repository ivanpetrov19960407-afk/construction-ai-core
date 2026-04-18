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


def test_session_store_keeps_documents_by_doc_type():
    """Один session_id должен хранить несколько типов документов без перезаписи."""

    async def _run() -> None:
        generate.SESSION_STORE.clear()

        generate._touch_session("shared-session", text="TK text", doc_type="tk", docx_bytes=b"tk")
        generate._touch_session(
            "shared-session", text="Letter text", doc_type="letter", docx_bytes=b"letter"
        )

        tk_session = generate._get_live_session("shared-session", expected_doc_type="tk")
        letter_session = generate._get_live_session("shared-session", expected_doc_type="letter")

        assert tk_session is not None
        assert letter_session is not None
        assert tk_session["docx_bytes"] == b"tk"
        assert letter_session["docx_bytes"] == b"letter"

    asyncio.run(_run())


def test_tk_download_falls_back_to_session_memory():
    """Если in-memory сессия пуста, download должен брать DOCX из persistent storage."""

    async def _run() -> None:
        old_keys = settings.api_keys
        old_get_docs = generate.session_memory.get_session_documents
        settings.api_keys = ["valid-key"]
        generate.SESSION_STORE.clear()
        generate.session_memory.get_session_documents = AsyncMock(
            return_value=[{"doc_type": "tk", "docx_bytes": b"persisted-docx"}]
        )

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                download_response = await client.get(
                    "/api/generate/tk/session-from-db/download",
                    headers={"X-API-Key": "valid-key"},
                )
        finally:
            settings.api_keys = old_keys
            generate.session_memory.get_session_documents = old_get_docs

        assert download_response.status_code == 200
        assert download_response.content == b"persisted-docx"

    asyncio.run(_run())
