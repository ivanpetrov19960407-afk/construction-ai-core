"""Тесты интеграции с ИСУП."""

from __future__ import annotations

import asyncio

import httpx

from config.settings import settings
from core.integrations import isup


class _MockResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _MockAsyncClient:
    def __init__(self, scripted: list[object]):
        self._scripted = scripted

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None

    async def post(self, *args, **kwargs):
        _ = (args, kwargs)
        action = self._scripted.pop(0)
        if isinstance(action, Exception):
            raise action
        return _MockResponse(action)

    async def get(self, *args, **kwargs):
        _ = (args, kwargs)
        action = self._scripted.pop(0)
        if isinstance(action, Exception):
            raise action
        return _MockResponse(action)


def test_submit_document_success(monkeypatch):
    old_url = settings.isup_api_url
    old_client_id = settings.isup_client_id
    old_secret = settings.isup_client_secret
    settings.isup_api_url = "https://isup.local"
    settings.isup_client_id = "client"
    settings.isup_client_secret = "secret"

    scripted = [
        {"access_token": "token-1"},
        {"submission_id": "sub-1", "status": "accepted"},
    ]
    monkeypatch.setattr(isup.httpx, "AsyncClient", lambda **kwargs: _MockAsyncClient(scripted))

    try:
        client = isup.ISUPClient()
        result = asyncio.run(
            client.submit_document(
                {"project_code": "P-1", "doc_type": "aosr", "file_b64": "ZmFrZQ=="}
            )
        )
    finally:
        settings.isup_api_url = old_url
        settings.isup_client_id = old_client_id
        settings.isup_client_secret = old_secret

    assert result["submission_id"] == "sub-1"
    assert result["status"] == "accepted"


def test_submit_document_retry_on_timeout(monkeypatch):
    old_url = settings.isup_api_url
    old_client_id = settings.isup_client_id
    old_secret = settings.isup_client_secret
    settings.isup_api_url = "https://isup.local"
    settings.isup_client_id = "client"
    settings.isup_client_secret = "secret"

    scripted = [
        {"access_token": "token-1"},
        httpx.ReadTimeout("timeout"),
        {"submission_id": "sub-2", "status": "accepted"},
    ]
    monkeypatch.setattr(isup.httpx, "AsyncClient", lambda **kwargs: _MockAsyncClient(scripted))

    try:
        client = isup.ISUPClient(max_retries=2)
        result = asyncio.run(
            client.submit_document(
                {"project_code": "P-2", "doc_type": "ks2", "file_b64": "ZmFrZQ=="}
            )
        )
    finally:
        settings.isup_api_url = old_url
        settings.isup_client_id = old_client_id
        settings.isup_client_secret = old_secret

    assert result["submission_id"] == "sub-2"


def test_get_status(monkeypatch):
    old_url = settings.isup_api_url
    old_client_id = settings.isup_client_id
    old_secret = settings.isup_client_secret
    settings.isup_api_url = "https://isup.local"
    settings.isup_client_id = "client"
    settings.isup_client_secret = "secret"

    scripted = [
        {"access_token": "token-2"},
        {"submission_id": "sub-3", "status": "processing"},
    ]
    monkeypatch.setattr(isup.httpx, "AsyncClient", lambda **kwargs: _MockAsyncClient(scripted))

    try:
        client = isup.ISUPClient()
        status = asyncio.run(client.get_submission_status("sub-3"))
    finally:
        settings.isup_api_url = old_url
        settings.isup_client_id = old_client_id
        settings.isup_client_secret = old_secret

    assert status["status"] == "processing"
