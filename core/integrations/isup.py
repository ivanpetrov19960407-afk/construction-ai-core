"""Интеграция с ИСУП Минстроя."""

from __future__ import annotations

import asyncio
import datetime as dt
from typing import Any
from uuid import uuid4

import httpx
from sqlalchemy import create_engine, text

from config.settings import settings

UTC = getattr(dt, "UTC", dt.timezone(dt.timedelta(0)))


class ISUPClient:
    """Клиент REST API ИСУП Минстроя."""

    def __init__(self, timeout: float = 30.0, max_retries: int = 2) -> None:
        self.base_url = settings.isup_api_url.rstrip("/")
        self.client_id = settings.isup_client_id
        self.client_secret = settings.isup_client_secret
        self.timeout = timeout
        self.max_retries = max_retries

    async def authenticate(self) -> str:
        """OAuth2 client_credentials → access_token."""
        token_url = f"{self.base_url}/oauth2/token"
        payload = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(token_url, data=payload)
            response.raise_for_status()
            body = response.json()

        token = str(body.get("access_token") or "")
        if not token:
            raise RuntimeError("ISUP OAuth2 response does not contain access_token")
        return token

    async def submit_document(self, doc: dict[str, Any]) -> dict[str, Any]:
        """Передача ИД-документа в ИСУП."""
        access_token = await self.authenticate()
        url = f"{self.base_url}/api/v2/documents/submit"
        headers = {"Authorization": f"Bearer {access_token}"}

        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(url, json=doc, headers=headers)
                    response.raise_for_status()
                    return response.json()
            except httpx.TimeoutException:
                if attempt >= self.max_retries:
                    raise
                await asyncio.sleep(0.2 * (attempt + 1))

        raise RuntimeError("ISUP submission failed after retries")

    async def get_submission_status(self, submission_id: str) -> dict[str, Any]:
        """Статус переданного документа."""
        access_token = await self.authenticate()
        url = f"{self.base_url}/api/v2/documents/{submission_id}/status"
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()

    async def submit_exec_album(self, project_id: str, section: str) -> dict[str, Any]:
        """Загрузить исполнительный альбом целиком."""
        payload = {"project_id": project_id, "section": section, "doc_type": "exec_album"}
        return await self.submit_document(payload)


def _save_isup_submission(
    *,
    project_id: str,
    doc_id: str,
    submission_id: str,
    status: str,
    response_json: dict[str, Any],
) -> None:
    engine = create_engine(settings.database_url, future=True)
    query = text(
        """
        INSERT INTO isup_submissions (
            id, project_id, doc_id, submission_id, status, submitted_at, response_json
        )
        VALUES (
            :id, :project_id, :doc_id, :submission_id, :status, :submitted_at, :response_json
        )
        """
    )
    with engine.begin() as conn:
        conn.execute(
            query,
            {
                "id": str(uuid4()),
                "project_id": project_id,
                "doc_id": doc_id,
                "submission_id": submission_id,
                "status": status,
                "submitted_at": dt.datetime.now(UTC),
                "response_json": response_json,
            },
        )


def _fetch_doc_payload(doc_id: str) -> dict[str, Any] | None:
    engine = create_engine(settings.database_url, future=True)
    query = text(
        """
        SELECT id, project_id, doc_type, pdf_url
        FROM executive_docs
        WHERE id = :doc_id
        LIMIT 1
        """
    )
    with engine.connect() as conn:
        row = conn.execute(query, {"doc_id": doc_id}).mappings().first()

    if row is None:
        return None

    return {
        "doc_id": str(row["id"]),
        "project_id": str(row["project_id"]),
        "project_code": str(row["project_id"]),
        "doc_type": str(row["doc_type"]),
        "file_b64": str(row.get("pdf_url") or ""),
    }


def _is_project_state_contract(project_id: str) -> bool:
    engine = create_engine(settings.database_url, future=True)
    query = text(
        """
        SELECT COALESCE(is_state_contract, 0) AS is_state_contract
        FROM projects
        WHERE id = :project_id
        LIMIT 1
        """
    )
    with engine.connect() as conn:
        row = conn.execute(query, {"project_id": project_id}).mappings().first()
    return bool(row and row.get("is_state_contract"))


async def submit_document_if_state_contract(doc_id: str) -> dict[str, Any] | None:
    """Отправить подписанный документ в ИСУП, если проект госзаказа."""
    if not settings.isup_enabled:
        return None

    payload = await asyncio.to_thread(_fetch_doc_payload, doc_id)
    if not payload:
        return None

    if not await asyncio.to_thread(_is_project_state_contract, payload["project_id"]):
        return None

    client = ISUPClient()
    response = await client.submit_document(payload)

    submission_id = str(response.get("submission_id") or response.get("id") or "")
    if submission_id:
        await asyncio.to_thread(
            _save_isup_submission,
            project_id=payload["project_id"],
            doc_id=payload["doc_id"],
            submission_id=submission_id,
            status=str(response.get("status") or "submitted"),
            response_json=response,
        )
    return response
