"""Tests for ISUP callback and submissions polling routes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app
from api.routes.auth import _create_token
from api.routes import isup as isup_routes
from config.settings import settings


class _FakeBeginConn:
    def __init__(self):
        self.executed: list[dict[str, object]] = []

    def execute(self, query, params):
        self.executed.append({"query": str(query), "params": params})


class _FakeBeginContext:
    def __init__(self, conn: _FakeBeginConn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        return None


class _FakeMappingsResult:
    def __init__(self, rows: list[dict[str, object]]):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSelectResult:
    def __init__(self, rows: list[dict[str, object]]):
        self._rows = rows

    def mappings(self):
        return _FakeMappingsResult(self._rows)


class _FakeConnectConn:
    def __init__(self, rows: list[dict[str, object]]):
        self._rows = rows

    def execute(self, query, params):
        _ = (query, params)
        return _FakeSelectResult(self._rows)


class _FakeConnectContext:
    def __init__(self, conn: _FakeConnectConn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        return None


class _FakeEngine:
    def __init__(self, rows: list[dict[str, object]] | None = None):
        self.begin_conn = _FakeBeginConn()
        self.connect_conn = _FakeConnectConn(rows or [])

    def begin(self):
        return _FakeBeginContext(self.begin_conn)

    def connect(self):
        return _FakeConnectContext(self.connect_conn)


def test_callback_updates_status(monkeypatch):
    old_keys = settings.api_keys
    old_secret = settings.isup_webhook_secret
    settings.api_keys = ["test-key"]
    settings.isup_webhook_secret = "super-secret"
    engine = _FakeEngine()
    monkeypatch.setattr(isup_routes, "create_engine", lambda *args, **kwargs: engine)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/isup/callback",
                json={"submission_id": "sub-123", "status": "accepted", "comment": "ok"},
                headers={
                    "X-API-Key": "test-key",
                    "X-ISUP-Webhook-Secret": "super-secret",
                },
            )
    finally:
        settings.api_keys = old_keys
        settings.isup_webhook_secret = old_secret

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert len(engine.begin_conn.executed) == 1
    params = engine.begin_conn.executed[0]["params"]
    assert params["submission_id"] == "sub-123"
    assert params["status"] == "accepted"
    assert '"callback_status": "accepted"' in params["patch"]
    assert '"comment": "ok"' in params["patch"]


def test_list_submissions(monkeypatch):
    old_keys = settings.api_keys
    token = _create_token("alice", "admin")
    settings.api_keys = ["test-key"]
    rows = [
        {
            "submission_id": "sub-1",
            "doc_id": "doc-1",
            "status": "processing",
            "submitted_at": "2026-04-16T10:00:00Z",
        },
        {
            "submission_id": "sub-2",
            "doc_id": "doc-2",
            "status": "accepted",
            "submitted_at": "2026-04-16T09:00:00Z",
        },
    ]
    engine = _FakeEngine(rows=rows)
    monkeypatch.setattr(isup_routes, "create_engine", lambda *args, **kwargs: engine)
    monkeypatch.setattr(isup_routes, "_require_project_access", lambda *args, **kwargs: None)

    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/isup/submissions/00000000-0000-0000-0000-000000000001",
                headers={"Authorization": f"Bearer {token}"},
            )
    finally:
        settings.api_keys = old_keys

    assert response.status_code == 200
    assert response.json() == {"submissions": rows}


def test_callback_rejects_invalid_secret(monkeypatch):
    old_keys = settings.api_keys
    old_secret = settings.isup_webhook_secret
    settings.api_keys = ["test-key"]
    settings.isup_webhook_secret = "expected-secret"
    engine = _FakeEngine()
    monkeypatch.setattr(isup_routes, "create_engine", lambda *args, **kwargs: engine)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/isup/callback",
                json={"submission_id": "sub-123", "status": "accepted", "comment": "ok"},
                headers={"X-API-Key": "test-key", "X-ISUP-Webhook-Secret": "wrong-secret"},
            )
    finally:
        settings.api_keys = old_keys
        settings.isup_webhook_secret = old_secret

    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid webhook secret"
    assert engine.begin_conn.executed == []
