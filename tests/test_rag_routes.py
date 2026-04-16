"""Tests for RAG management endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app
from api.routes import rag as rag_routes
from api.routes.auth import _create_token
from config.settings import settings


class _DummyCollection:
    def __init__(self, metadatas: list[dict]):
        self._metadatas = metadatas

    def get(self, include: list[str] | None = None) -> dict:
        return {"metadatas": self._metadatas}


class _DummyRAGEngine:
    def __init__(self):
        self.collection = _DummyCollection(
            [
                {"source": "sp_48.pdf"},
                {"source": "sp_48.pdf"},
                {"source": "gost_21.pdf"},
            ]
        )

    def ingest_pdf(self, filepath: str, source_name: str, metadata: dict | None = None) -> int:
        assert filepath.endswith(".pdf")
        assert source_name == "sp_48.pdf"
        return 7


def test_rag_ingest_pdf_success(monkeypatch):
    old_api_keys = settings.api_keys
    old_admin_keys = settings.admin_api_keys
    settings.api_keys = ["admin-key"]
    settings.admin_api_keys = ["admin-key"]

    monkeypatch.setattr(rag_routes, "get_rag_engine", lambda: _DummyRAGEngine())

    parse_called = {"ok": False}

    def _fake_parse(file_bytes: bytes, filename: str):
        parse_called["ok"] = True
        assert filename == "sp_48.pdf"
        assert file_bytes.startswith(b"%PDF")
        return object()

    monkeypatch.setattr(rag_routes.pdf_parser, "parse", _fake_parse)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/rag/ingest",
                files={
                    "file": ("sp_48.pdf", b"%PDF-1.4 fake", "application/pdf"),
                    "source_name": (None, "sp_48.pdf"),
                },
                headers={"X-API-Key": "admin-key"},
            )
    finally:
        settings.api_keys = old_api_keys
        settings.admin_api_keys = old_admin_keys

    assert response.status_code == 200
    assert response.json() == {"chunks_added": 7, "source": "sp_48.pdf"}
    assert parse_called["ok"] is True


def test_rag_sources_requires_admin_and_returns_counts(monkeypatch):
    old_api_keys = settings.api_keys
    old_admin_keys = settings.admin_api_keys
    settings.api_keys = ["valid-key", "admin-key"]
    settings.admin_api_keys = ["admin-key"]

    monkeypatch.setattr(rag_routes, "get_rag_engine", lambda: _DummyRAGEngine())

    try:
        with TestClient(app) as client:
            forbidden = client.get(
                "/api/rag/sources",
                headers={"X-API-Key": "valid-key"},
            )
            ok = client.get(
                "/api/rag/sources",
                headers={"X-API-Key": "admin-key"},
            )
    finally:
        settings.api_keys = old_api_keys
        settings.admin_api_keys = old_admin_keys

    assert forbidden.status_code == 403
    assert forbidden.json() == {"detail": "Admin role required"}

    assert ok.status_code == 200
    assert ok.json() == {
        "sources": [
            {"source": "gost_21.pdf", "chunks": 1},
            {"source": "sp_48.pdf", "chunks": 2},
        ]
    }


def test_rag_sources_allows_admin_jwt(monkeypatch):
    old_api_keys = settings.api_keys
    old_admin_keys = settings.admin_api_keys
    settings.api_keys = ["valid-key"]
    settings.admin_api_keys = []

    monkeypatch.setattr(rag_routes, "get_rag_engine", lambda: _DummyRAGEngine())

    admin_token = _create_token("admin-user", "admin")
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/rag/sources",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
    finally:
        settings.api_keys = old_api_keys
        settings.admin_api_keys = old_admin_keys

    assert response.status_code == 200
    assert response.json() == {
        "sources": [
            {"source": "gost_21.pdf", "chunks": 1},
            {"source": "sp_48.pdf", "chunks": 2},
        ]
    }
