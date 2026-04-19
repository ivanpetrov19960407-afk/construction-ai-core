"""Authorization tests for RAG personal/global sources."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app
from api.routes import rag as rag_routes
from api.routes.auth import _create_token
from config.settings import settings


class _DummyCollection:
    def __init__(self, metadatas: list[dict], ids: list[str] | None = None):
        self._metadatas = metadatas
        self._ids = ids or [f"id-{i}" for i in range(len(metadatas))]

    def get(self, include: list[str] | None = None) -> dict:
        return {"metadatas": self._metadatas, "ids": self._ids}

    def delete(self, ids: list[str]) -> None:
        self._ids = [doc_id for doc_id in self._ids if doc_id not in set(ids)]


class _DummyRAGEngine:
    def __init__(self):
        self.collection = _DummyCollection(
            [
                {"source": "global.pdf"},
                {"source": "my.pdf", "username": "pto"},
                {"source": "my.pdf", "username": "pto"},
                {"source": "other.pdf", "username": "other"},
            ]
        )

    def ingest_pdf(self, filepath: str, source_name: str, metadata: dict | None = None) -> int:
        assert filepath.endswith(".pdf")
        if metadata:
            assert metadata.get("username") == "pto"
        return 2


def test_pto_forbidden_on_global_sources_and_allowed_on_personal(monkeypatch):
    old_api_keys = settings.api_keys
    old_admin_keys = settings.admin_api_keys
    settings.api_keys = []
    settings.admin_api_keys = []

    monkeypatch.setattr(rag_routes, "get_rag_engine", lambda: _DummyRAGEngine())

    token = _create_token("pto", "pto_engineer")
    with TestClient(app) as client:
        forbidden = client.get("/api/rag/sources", headers={"Authorization": f"Bearer {token}"})
        my_sources = client.get("/api/rag/my-sources", headers={"Authorization": f"Bearer {token}"})

    settings.api_keys = old_api_keys
    settings.admin_api_keys = old_admin_keys

    assert forbidden.status_code == 403
    assert my_sources.status_code == 200
    assert my_sources.json() == {"sources": [{"source": "my.pdf", "chunks": 2}]}


def test_pto_can_chat_upload(monkeypatch):
    old_api_keys = settings.api_keys
    old_admin_keys = settings.admin_api_keys
    settings.api_keys = []
    settings.admin_api_keys = []

    monkeypatch.setattr(rag_routes, "get_rag_engine", lambda: _DummyRAGEngine())
    monkeypatch.setattr(rag_routes.pdf_parser, "parse", lambda file_bytes, filename: object())

    token = _create_token("pto", "pto_engineer")
    with TestClient(app) as client:
        response = client.post(
            "/api/rag/chat-upload",
            files={
                "file": ("my.pdf", b"%PDF-1.4 fake", "application/pdf"),
                "session_id": (None, "chat-pto"),
            },
            headers={"Authorization": f"Bearer {token}"},
        )

    settings.api_keys = old_api_keys
    settings.admin_api_keys = old_admin_keys

    assert response.status_code == 200
    assert response.json() == {"chunks_added": 2, "source": "my.pdf"}
