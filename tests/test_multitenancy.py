"""Tests for org_id multitenancy isolation."""

from fastapi.testclient import TestClient

from api.main import app
from api.routes.auth import _create_token
from config.settings import settings
from core import projects as projects_core


def _auth_headers(username: str, org_id: str | None = None) -> dict[str, str]:
    token = _create_token(username, "pto_engineer", org_id or "default")
    return {"Authorization": f"Bearer {token}"}


def _with_temp_db(tmp_path):
    old = settings.sqlite_db_path
    settings.sqlite_db_path = str(tmp_path / "projects_multitenancy.db")
    projects_core._ENGINE_CACHE.clear()
    projects_core._SESSIONMAKER_CACHE.clear()
    return old


def test_tenant_isolation(tmp_path):
    old_db_path = _with_temp_db(tmp_path)
    try:
        with TestClient(app) as client:
            alpha_create = client.post(
                "/api/projects",
                json={"name": "Alpha", "description": "Org A", "members": []},
                headers=_auth_headers("ivan", "org-alpha"),
            )
            beta_create = client.post(
                "/api/projects",
                json={"name": "Beta", "description": "Org B", "members": []},
                headers=_auth_headers("ivan", "org-beta"),
            )

            alpha_list = client.get("/api/projects", headers=_auth_headers("ivan", "org-alpha"))
            beta_list = client.get("/api/projects", headers=_auth_headers("ivan", "org-beta"))
    finally:
        settings.sqlite_db_path = old_db_path
        projects_core._ENGINE_CACHE.clear()
        projects_core._SESSIONMAKER_CACHE.clear()

    assert alpha_create.status_code == 201
    assert beta_create.status_code == 201

    alpha_projects = alpha_list.json()["projects"]
    beta_projects = beta_list.json()["projects"]

    assert [item["name"] for item in alpha_projects] == ["Alpha"]
    assert [item["name"] for item in beta_projects] == ["Beta"]


def test_default_tenant_backward_compat(tmp_path):
    old_db_path = _with_temp_db(tmp_path)
    try:
        with TestClient(app) as client:
            create_response = client.post(
                "/api/projects",
                json={"name": "Legacy", "description": "No org claim", "members": []},
                headers=_auth_headers("legacy-user"),
            )
            list_response = client.get("/api/projects", headers=_auth_headers("legacy-user"))
    finally:
        settings.sqlite_db_path = old_db_path
        projects_core._ENGINE_CACHE.clear()
        projects_core._SESSIONMAKER_CACHE.clear()

    assert create_response.status_code == 201
    assert list_response.status_code == 200
    projects = list_response.json()["projects"]
    assert len(projects) == 1
    assert projects[0]["name"] == "Legacy"
    assert projects[0]["org_id"] == "default"
