"""Tests for Telegram/Desktop linking and notification polling."""

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from api.main import app
from api.routes import generate
from config.settings import settings
from core.session_bridge import issue_telegram_link_token


def test_link_telegram_and_fetch_notifications(tmp_path):
    old_keys = settings.api_keys
    old_db_path = settings.sqlite_db_path

    settings.api_keys = ["valid-key"]
    settings.sqlite_db_path = str(tmp_path / "linking.db")

    token = issue_telegram_link_token(telegram_user_id=123456, session_id="123456")

    try:
        with TestClient(app) as client:
            link_response = client.post(
                "/api/link/telegram",
                json={"code": token, "user_id": "desktop-user-1", "session_id": "desktop-session-1"},
                headers={"X-API-Key": "valid-key"},
            )
            assert link_response.status_code == 200
            assert link_response.json()["telegram_user_id"] == "123456"

            mocked_process = AsyncMock(
                return_value={
                    "session_id": "123456",
                    "reply": "ok",
                    "agents_used": ["formatter"],
                    "confidence": 0.9,
                    "state": {"docx_payload": {"title": "ТК"}},
                }
            )
            generate.orchestrator.process = mocked_process

            generate_response = client.post(
                "/api/generate/tk",
                json={
                    "work_type": "бетонирование",
                    "object_name": "ЖК",
                    "volume": 1,
                    "unit": "м³",
                    "session_id": "123456",
                    "role": "pto_engineer",
                },
                headers={"X-API-Key": "valid-key"},
            )
            assert generate_response.status_code == 200

            notifications_response = client.get(
                "/api/notifications?user_id=desktop-user-1",
                headers={"X-API-Key": "valid-key"},
            )
            assert notifications_response.status_code == 200
            notifications = notifications_response.json()["notifications"]
            assert len(notifications) == 1
            assert notifications[0]["event_type"] == "document_ready"
            assert notifications[0]["session_id"] == "desktop-session-1"

            # unread notifications are marked as read after first poll
            second_fetch = client.get(
                "/api/notifications?user_id=desktop-user-1",
                headers={"X-API-Key": "valid-key"},
            )
            assert second_fetch.status_code == 200
            assert second_fetch.json()["notifications"] == []
    finally:
        settings.api_keys = old_keys
        settings.sqlite_db_path = old_db_path
