"""Tests for project collaboration endpoints."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from api.main import app
from api.routes.auth import _create_token
from config.settings import settings
from core import billing as billing_core
from core import projects as projects_core


def _auth_headers(username: str) -> dict[str, str]:
    token = _create_token(username, "pto_engineer")
    return {"Authorization": f"Bearer {token}"}


def _with_temp_db(tmp_path):
    old = settings.sqlite_db_path
    settings.sqlite_db_path = str(tmp_path / "projects.db")
    projects_core._ENGINE_CACHE.clear()
    projects_core._SESSIONMAKER_CACHE.clear()
    return old


def test_create_project(tmp_path):
    old_db_path = _with_temp_db(tmp_path)
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/projects",
                json={"name": "ЖК Север", "description": "Фасадные работы", "members": ["petr"]},
                headers=_auth_headers("ivan"),
            )
    finally:
        settings.sqlite_db_path = old_db_path
        projects_core._ENGINE_CACHE.clear()
        projects_core._SESSIONMAKER_CACHE.clear()

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "ЖК Север"
    assert set(data["members"]) == {"ivan", "petr"}
    assert isinstance(data["short_id"], int)


def test_add_member(tmp_path):
    old_db_path = _with_temp_db(tmp_path)
    try:
        with TestClient(app) as client:
            create = client.post(
                "/api/projects",
                json={"name": "Мост", "description": "Бетон", "members": []},
                headers=_auth_headers("owner"),
            )
            project_id = create.json()["id"]
            add_member = client.post(
                f"/api/projects/{project_id}/members",
                json={"member_id": "worker"},
                headers=_auth_headers("owner"),
            )
    finally:
        settings.sqlite_db_path = old_db_path
        projects_core._ENGINE_CACHE.clear()
        projects_core._SESSIONMAKER_CACHE.clear()

    assert add_member.status_code == 200
    assert "worker" in add_member.json()["members"]


def test_add_document_to_project(tmp_path):
    old_db_path = _with_temp_db(tmp_path)
    try:
        with TestClient(app) as client:
            create = client.post(
                "/api/projects",
                json={"name": "Школа", "description": "Раздел АР", "members": ["member"]},
                headers=_auth_headers("owner"),
            )
            project_id = create.json()["id"]
            response = client.post(
                f"/api/projects/{project_id}/documents",
                json={
                    "document_type": "tk",
                    "session_id": "sess-1",
                    "title": "Технологическая карта",
                    "version": 2,
                },
                headers=_auth_headers("member"),
            )
            documents = client.get(
                f"/api/projects/{project_id}/documents",
                headers=_auth_headers("owner"),
            )
    finally:
        settings.sqlite_db_path = old_db_path
        projects_core._ENGINE_CACHE.clear()
        projects_core._SESSIONMAKER_CACHE.clear()

    assert response.status_code == 201
    assert response.json()["session_id"] == "sess-1"
    assert documents.status_code == 200
    assert len(documents.json()["documents"]) == 1


def test_get_history(tmp_path):
    old_db_path = _with_temp_db(tmp_path)
    try:
        with TestClient(app) as client:
            create = client.post(
                "/api/projects",
                json={"name": "БЦ", "description": "Документы", "members": ["member"]},
                headers=_auth_headers("owner"),
            )
            project_id = create.json()["id"]
            doc = client.post(
                f"/api/projects/{project_id}/documents",
                json={
                    "document_type": "letter",
                    "session_id": "sess-history",
                    "title": "Письмо заказчику",
                    "version": 1,
                },
                headers=_auth_headers("owner"),
            )
            doc_id = doc.json()["id"]
            comment = client.post(
                f"/api/projects/{project_id}/documents/{doc_id}/comments",
                json={"text": "Нужно обновить реквизиты"},
                headers=_auth_headers("member"),
            )
            history = client.get(
                f"/api/projects/{project_id}/history",
                headers=_auth_headers("owner"),
            )
    finally:
        settings.sqlite_db_path = old_db_path
        projects_core._ENGINE_CACHE.clear()
        projects_core._SESSIONMAKER_CACHE.clear()

    assert comment.status_code == 201
    assert history.status_code == 200
    items = history.json()["history"]
    assert len(items) >= 3
    assert {item["type"] for item in items}.issuperset(
        {"project_created", "document_added", "comment_added"},
    )


def test_query_param_user_id_does_not_authorize(tmp_path):
    old_db_path = _with_temp_db(tmp_path)
    old_api_keys = settings.api_keys
    settings.api_keys = ["test-key"]
    try:
        with TestClient(app) as client:
            create = client.post(
                "/api/projects",
                json={"name": "Secure", "description": "Auth only", "members": []},
                headers=_auth_headers("owner"),
            )
            project_id = create.json()["id"]

            response = client.get(
                f"/api/projects/{project_id}?user_id=owner",
                headers={"X-API-Key": "test-key"},
            )
    finally:
        settings.sqlite_db_path = old_db_path
        settings.api_keys = old_api_keys
        projects_core._ENGINE_CACHE.clear()
        projects_core._SESSIONMAKER_CACHE.clear()

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}


def test_list_my_projects_alias(tmp_path):
    old_db_path = _with_temp_db(tmp_path)
    try:
        with TestClient(app) as client:
            client.post(
                "/api/projects",
                json={"name": "Mine", "description": "Only mine", "members": []},
                headers=_auth_headers("owner"),
            )
            mine = client.get("/api/projects/mine", headers=_auth_headers("owner"))
    finally:
        settings.sqlite_db_path = old_db_path
        projects_core._ENGINE_CACHE.clear()
        projects_core._SESSIONMAKER_CACHE.clear()

    assert mine.status_code == 200
    assert len(mine.json()["projects"]) == 1


def _bind_api_key_user(users_db_path: str, api_key: str, username: str) -> None:
    users_db = Path(users_db_path)
    users_db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(users_db) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS api_keys (
                api_key TEXT PRIMARY KEY,
                user_id TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT OR REPLACE INTO api_keys (api_key, user_id) VALUES (?, ?)",
            (api_key, username),
        )
        connection.commit()


def test_api_key_project_creation_consumes_quota(tmp_path, monkeypatch):
    old_db_path = _with_temp_db(tmp_path)
    old_users_db = settings.users_db_path
    old_api_keys = settings.api_keys
    settings.users_db_path = str(tmp_path / "users.db")
    settings.api_keys = ["test-key"]
    _bind_api_key_user(settings.users_db_path, "test-key", "owner")

    called: dict[str, str | None] = {"org_id": None}

    async def _consume_quota(org_id: str, resource: str, plan):
        _ = resource, plan
        called["org_id"] = org_id
        return True

    monkeypatch.setattr(billing_core.usage_counter, "consume_quota", _consume_quota)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/projects",
                json={"name": "API Key", "description": "Quota", "members": []},
                headers={"X-API-Key": "test-key"},
            )
    finally:
        settings.sqlite_db_path = old_db_path
        settings.users_db_path = old_users_db
        settings.api_keys = old_api_keys
        projects_core._ENGINE_CACHE.clear()
        projects_core._SESSIONMAKER_CACHE.clear()

    assert response.status_code == 201
    assert called["org_id"] == "default"
