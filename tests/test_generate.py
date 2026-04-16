"""Тесты для /api/generate/exec-album."""

from fastapi.testclient import TestClient

from api.main import app
from api.routes import generate
from config.settings import settings


def test_exec_album_endpoint(monkeypatch):
    """POST /api/generate/exec-album возвращает URL собранного альбома."""
    old_keys = settings.api_keys
    settings.api_keys = ["valid-key"]

    def _mock_fetch_approved_exec_docs(project_id: str, section: str) -> list[dict]:
        assert project_id == "project-1"
        assert section == "AR"
        return [
            {
                "id": "doc-1",
                "pdf_url": "https://storage.local/doc-1.pdf",
                "created_at": "2026-01-10T10:00:00Z",
            },
            {
                "id": "doc-2",
                "pdf_url": "https://storage.local/doc-2.pdf",
                "created_at": "2026-01-11T10:00:00Z",
            },
        ]

    def _mock_render_exec_album_pdf(project_id: str, section: str, docs: list[dict]) -> bytes:
        assert project_id == "project-1"
        assert section == "AR"
        assert len(docs) == 2
        return b"%PDF-1.4\nmock"

    def _mock_upload_album_bytes(project_id: str, section: str, pdf_bytes: bytes) -> str:
        assert project_id == "project-1"
        assert section == "AR"
        assert pdf_bytes.startswith(b"%PDF")
        return "https://storage.local/presigned/project-1/AR_latest.pdf"

    monkeypatch.setattr(generate, "_fetch_approved_exec_docs", _mock_fetch_approved_exec_docs)
    monkeypatch.setattr(generate, "_render_exec_album_pdf", _mock_render_exec_album_pdf)
    monkeypatch.setattr(generate, "_upload_album_bytes", _mock_upload_album_bytes)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/generate/exec-album",
                json={"project_id": "project-1", "section": "AR"},
                headers={"X-API-Key": "valid-key"},
            )
    finally:
        settings.api_keys = old_keys

    assert response.status_code == 200
    data = response.json()
    assert "url" in data
    assert data["section"] == "AR"
    assert data["doc_count"] == 2
