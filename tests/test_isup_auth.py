"""Authorization tests for ISUP submission routes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app
from api.routes import isup as isup_routes
from api.routes.auth import _create_token
from config.settings import settings


class _FakeRowResult:
    def __init__(self, row: dict[str, object] | None):
        self._row = row

    def mappings(self):
        return self

    def first(self):
        return self._row


class _FakeConn:
    def __init__(self, row: dict[str, object] | None):
        self._row = row

    def execute(self, query, params):
        _ = (query, params)
        return _FakeRowResult(self._row)


class _FakeConnectContext:
    def __init__(self, conn: _FakeConn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        return None


class _FakeEngine:
    def __init__(self, row: dict[str, object] | None):
        self._row = row

    def connect(self):
        return _FakeConnectContext(_FakeConn(self._row))


def test_submit_document_rejects_api_key_without_user_context(monkeypatch):
    old_enabled = settings.isup_enabled
    old_keys = settings.api_keys
    settings.isup_enabled = True
    settings.api_keys = ["test-key"]

    monkeypatch.setattr(
        isup_routes,
        "_fetch_doc_payload",
        lambda doc_id: {"doc_id": doc_id, "project_id": "project-1"},
    )

    class _Client:
        async def submit_document(self, doc_payload):
            _ = doc_payload
            return {"submission_id": "sub-1"}

    monkeypatch.setattr(isup_routes, "ISUPClient", lambda: _Client())

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/isup/submit-document",
                json={"project_id": "project-1", "doc_id": "doc-1"},
                headers={"X-API-Key": "test-key"},
            )
    finally:
        settings.isup_enabled = old_enabled
        settings.api_keys = old_keys

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}


def test_submit_document_allows_member_with_jwt(monkeypatch):
    old_enabled = settings.isup_enabled
    settings.isup_enabled = True
    token = _create_token("member", "pto_engineer")

    monkeypatch.setattr(
        isup_routes,
        "_fetch_doc_payload",
        lambda doc_id: {"doc_id": doc_id, "project_id": "project-1"},
    )
    monkeypatch.setattr(
        isup_routes,
        "create_engine",
        lambda *args, **kwargs: _FakeEngine({"owner_id": "owner", "members": ["member"]}),
    )

    class _Client:
        async def submit_document(self, doc_payload):
            _ = doc_payload
            return {"submission_id": "sub-1", "status": "accepted"}

    monkeypatch.setattr(isup_routes, "ISUPClient", lambda: _Client())

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/isup/submit-document",
                json={"project_id": "project-1", "doc_id": "doc-1"},
                headers={"Authorization": f"Bearer {token}"},
            )
    finally:
        settings.isup_enabled = old_enabled

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["result"]["submission_id"] == "sub-1"
