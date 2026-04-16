"""Маршруты интеграции с ИСУП Минстроя."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from config.settings import settings
from core.integrations.isup import ISUPClient, _fetch_doc_payload

router = APIRouter(prefix="/api/isup", tags=["isup"])


class SubmitDocumentRequest(BaseModel):
    """Запрос на отправку конкретного документа в ИСУП."""

    project_id: str
    doc_id: str


class SubmitAlbumRequest(BaseModel):
    """Запрос на отправку исполнительного альбома по разделу."""

    project_id: str
    section: str


@router.post("/submit-document")
async def submit_document(payload: SubmitDocumentRequest, request: Request) -> dict:
    """Передать ИД-документ в ИСУП."""
    _ = request
    if not settings.isup_enabled:
        raise HTTPException(status_code=503, detail="ISUP integration is disabled")

    doc_payload = await asyncio.to_thread(_fetch_doc_payload, payload.doc_id)
    if not doc_payload:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc_payload["project_id"] != payload.project_id:
        raise HTTPException(status_code=400, detail="project_id does not match doc")

    result = await ISUPClient().submit_document(doc_payload)
    return {"ok": True, "result": result}


@router.post("/submit-album")
async def submit_album(payload: SubmitAlbumRequest, request: Request) -> dict:
    """Передать исполнительный альбом в ИСУП."""
    _ = request
    if not settings.isup_enabled:
        raise HTTPException(status_code=503, detail="ISUP integration is disabled")

    result = await ISUPClient().submit_exec_album(payload.project_id, payload.section)
    return {"ok": True, "result": result}


@router.get("/status/{submission_id}")
async def get_status(submission_id: str, request: Request) -> dict:
    """Получить статус отправки в ИСУП."""
    _ = request
    if not settings.isup_enabled:
        raise HTTPException(status_code=503, detail="ISUP integration is disabled")

    result = await ISUPClient().get_submission_status(submission_id)
    return {"ok": True, "result": result}
