"""Tests for project collaboration endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app
from api.routes.auth import _create_token
from config.settings import settings
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
        client = TestClient(app)
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


def test_add_member(tmp_path):
    old_db_path = _with_temp_db(tmp_path)
    try:
        client = TestClient(app)
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
        client = TestClient(app)
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
        client = TestClient(app)
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
    assert {item["type"] for item in items}.issuperset({"project_created", "document_added", "comment_added"})
