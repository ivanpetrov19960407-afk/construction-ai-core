"""Тесты для подписи и проверки подписей документов."""

from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from api.main import app
from api.routes import sign
from config.settings import settings


class _MockHTTPResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _MockAsyncClient:
    def __init__(self, payload: dict):
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None

    async def post(self, *args, **kwargs):
        _ = (args, kwargs)
        return _MockHTTPResponse(self._payload)


def test_sign_document(monkeypatch):
    old_keys = settings.api_keys
    old_rest_url = settings.CRYPTOPRO_REST_URL
    old_api_key = settings.CRYPTOPRO_API_KEY
    old_thumbprint = settings.CRYPTOPRO_CERT_THUMBPRINT
    settings.api_keys = ["valid-key"]
    settings.CRYPTOPRO_REST_URL = "https://cryptopro.local"
    settings.CRYPTOPRO_API_KEY = "crypto-key"
    settings.CRYPTOPRO_CERT_THUMBPRINT = "ORG-THUMB"

    updates: list[dict] = []

    monkeypatch.setattr(
        sign,
        "_fetch_exec_doc_for_sign",
        lambda doc_id, doc_type: {
            "id": doc_id,
            "doc_type": doc_type,
            "pdf_url": "https://storage.local/path/doc.pdf",
            "status": "approved",
        },
    )
    monkeypatch.setattr(sign, "_fetch_user_cert_thumbprint", lambda user_id: "USER-THUMB")

    async def _mock_download_binary(_: str) -> bytes:
        return b"%PDF-1.4 mock"

    monkeypatch.setattr(sign, "_download_binary", _mock_download_binary)
    monkeypatch.setattr(
        sign,
        "_upload_related_signed_files",
        lambda *_: (
            "https://storage.local/path/doc_signed.pdf",
            "https://storage.local/path/doc.sig",
        ),
    )

    def _mock_mark_document_signed(doc_id: str, user_id: str, sig_url: str) -> None:
        updates.append({"doc_id": doc_id, "user_id": user_id, "sig_url": sig_url})

    monkeypatch.setattr(sign, "_mark_document_signed", _mock_mark_document_signed)

    signed_data = base64.b64encode(b"%PDF signed").decode("utf-8")
    signature = base64.b64encode(b"SIG").decode("utf-8")
    monkeypatch.setattr(
        sign.httpx,
        "AsyncClient",
        lambda **kwargs: _MockAsyncClient(
            {"signed_data_b64": signed_data, "signature_b64": signature}
        ),
    )

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/sign/document",
                json={"doc_id": "doc-1", "doc_type": "aosr", "user_id": "user-1"},
                headers={"X-API-Key": "valid-key"},
            )
    finally:
        settings.api_keys = old_keys
        settings.CRYPTOPRO_REST_URL = old_rest_url
        settings.CRYPTOPRO_API_KEY = old_api_key
        settings.CRYPTOPRO_CERT_THUMBPRINT = old_thumbprint

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "signed"
    assert data["sig_url"].endswith(".sig")
    assert updates and updates[0]["doc_id"] == "doc-1"


def test_verify_valid(monkeypatch):
    old_keys = settings.api_keys
    old_rest_url = settings.CRYPTOPRO_REST_URL
    old_api_key = settings.CRYPTOPRO_API_KEY
    settings.api_keys = ["valid-key"]
    settings.CRYPTOPRO_REST_URL = "https://cryptopro.local"
    settings.CRYPTOPRO_API_KEY = "crypto-key"

    monkeypatch.setattr(
        sign,
        "_fetch_exec_doc_for_verify",
        lambda doc_id: {
            "id": doc_id,
            "pdf_url": "https://storage.local/path/doc.pdf",
            "sig_url": "https://storage.local/path/doc.sig",
            "signed_at": "2026-04-16T10:00:00Z",
        },
    )

    async def _mock_download_binary(_: str) -> bytes:
        return b"blob"

    monkeypatch.setattr(sign, "_download_binary", _mock_download_binary)
    monkeypatch.setattr(
        sign.httpx,
        "AsyncClient",
        lambda **kwargs: _MockAsyncClient(
            {"valid": True, "signer": "Ivan Petrov", "signed_at": "2026-04-16T10:00:00Z"}
        ),
    )

    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/sign/verify/doc-1",
                headers={"X-API-Key": "valid-key"},
            )
    finally:
        settings.api_keys = old_keys
        settings.CRYPTOPRO_REST_URL = old_rest_url
        settings.CRYPTOPRO_API_KEY = old_api_key

    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is True
    assert payload["signer"] == "Ivan Petrov"


def test_verify_invalid(monkeypatch):
    old_keys = settings.api_keys
    old_rest_url = settings.CRYPTOPRO_REST_URL
    old_api_key = settings.CRYPTOPRO_API_KEY
    settings.api_keys = ["valid-key"]
    settings.CRYPTOPRO_REST_URL = "https://cryptopro.local"
    settings.CRYPTOPRO_API_KEY = "crypto-key"

    monkeypatch.setattr(
        sign,
        "_fetch_exec_doc_for_verify",
        lambda doc_id: {
            "id": doc_id,
            "pdf_url": "https://storage.local/path/doc.pdf",
            "sig_url": "https://storage.local/path/doc.sig",
            "signed_at": "2026-04-16T10:00:00Z",
        },
    )

    async def _mock_download_binary(_: str) -> bytes:
        return b"blob"

    monkeypatch.setattr(sign, "_download_binary", _mock_download_binary)
    monkeypatch.setattr(
        sign.httpx,
        "AsyncClient",
        lambda **kwargs: _MockAsyncClient({"valid": False, "signer": ""}),
    )

    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/sign/verify/doc-2",
                headers={"X-API-Key": "valid-key"},
            )
    finally:
        settings.api_keys = old_keys
        settings.CRYPTOPRO_REST_URL = old_rest_url
        settings.CRYPTOPRO_API_KEY = old_api_key

    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is False
