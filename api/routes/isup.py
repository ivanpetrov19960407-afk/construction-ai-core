"""Маршруты интеграции с ИСУП Минстроя."""

from __future__ import annotations

import asyncio
import json
import secrets
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import create_engine, text

from config.settings import settings
from core.integrations.isup import ISUPClient, _fetch_doc_payload
from core.projects import Project, get_projects_sessionmaker

router = APIRouter(prefix="/api/isup", tags=["isup"])


class SubmitDocumentRequest(BaseModel):
    """Запрос на отправку конкретного документа в ИСУП."""

    project_id: str
    doc_id: str


class SubmitAlbumRequest(BaseModel):
    """Запрос на отправку исполнительного альбома по разделу."""

    project_id: str
    section: str


class ISUPCallbackPayload(BaseModel):
    """Payload вебхука обратного статуса из ИСУП."""

    submission_id: str
    status: str
    comment: str = ""


def _require_project_access(project_id: str, request: Request) -> None:
    username = getattr(request.state, "username", None)
    if not username:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        project_uuid = UUID(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid project ID") from exc

    session_local = get_projects_sessionmaker(settings.sqlite_db_path)
    with session_local() as session:
        project = session.get(Project, project_uuid)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

        members = project.members or []
        if username != project.owner_id and username not in members:
            raise HTTPException(status_code=403, detail="Access denied")


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


@router.post("/callback")
async def isup_status_callback(payload: ISUPCallbackPayload, request: Request) -> dict:
    """Вебхук от ИСУП: обновить статус отправки."""
    configured_secret = settings.isup_webhook_secret.strip()
    if not configured_secret:
        raise HTTPException(status_code=503, detail="ISUP webhook secret is not configured")

    provided_secret = request.headers.get("X-ISUP-Webhook-Secret", "")
    if not secrets.compare_digest(provided_secret, configured_secret):
        raise HTTPException(status_code=403, detail="Invalid webhook secret")

    engine = create_engine(settings.database_url, future=True)
    query = text(
        """
        UPDATE isup_submissions
        SET status = :status,
            response_json = json_patch(COALESCE(response_json, '{}'), :patch)
        WHERE submission_id = :submission_id
        """
    )
    patch_data = json.dumps({"callback_status": payload.status, "comment": payload.comment})
    with engine.begin() as conn:
        conn.execute(
            query,
            {"submission_id": payload.submission_id, "status": payload.status, "patch": patch_data},
        )
    return {"ok": True}


@router.get("/submissions/{project_id}")
async def list_isup_submissions(project_id: str, request: Request) -> dict:
    """Список отправок в ИСУП по проекту для polling из фронтенда."""
    _require_project_access(project_id, request)

    engine = create_engine(settings.database_url, future=True)
    with engine.connect() as conn:
        rows = (
            conn.execute(
                text(
                    """
                SELECT submission_id, doc_id, status, submitted_at
                FROM isup_submissions
                WHERE project_id = :pid
                ORDER BY submitted_at DESC
                """
                ),
                {"pid": project_id},
            )
            .mappings()
            .all()
        )
    return {"submissions": [dict(row) for row in rows]}
