"""Tests for auth routes and canonical profile endpoint contract."""

import asyncio
import sqlite3
from pathlib import Path

from httpx import ASGITransport, AsyncClient

from api.main import app
from config.settings import settings


def _register_user(client: AsyncClient, username: str, invite_code: str, password: str):
    return client.post(
        "/auth/register",
        json={
            "username": username,
            "password": password,
            "invite_code": invite_code,
        },
    )


def _configure_auth_test_state(tmp_path: Path) -> dict[str, object]:
    return {
        "users_db_path": settings.users_db_path,
        "invite_codes": settings.invite_codes,
        "jwt_secret": settings.jwt_secret,
        "api_keys": settings.api_keys,
        "admin_api_keys": settings.admin_api_keys,
        "new_users_db_path": str(tmp_path / "users.db"),
    }


def _apply_auth_test_state(state: dict[str, object]) -> None:
    settings.users_db_path = str(state["new_users_db_path"])
    settings.invite_codes = {"PTO-XXX": "pto_engineer", "ADMIN-XXX": "admin"}
    settings.jwt_secret = "test-secret"
    settings.api_keys = ["test-api-key-123456"]
    settings.admin_api_keys = ["test-api-key-123456"]


def _restore_auth_test_state(state: dict[str, object]) -> None:
    settings.users_db_path = str(state["users_db_path"])
    settings.invite_codes = state["invite_codes"]  # type: ignore[assignment]
    settings.jwt_secret = str(state["jwt_secret"])
    settings.api_keys = state["api_keys"]  # type: ignore[assignment]
    settings.admin_api_keys = state["admin_api_keys"]  # type: ignore[assignment]


def test_register_with_valid_invite_code(tmp_path: Path):
    """Register endpoint should create user with mapped role."""

    async def _run() -> None:
        state = _configure_auth_test_state(tmp_path)
        _apply_auth_test_state(state)
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await _register_user(client, "ivan", "PTO-XXX", "pass123")
        finally:
            _restore_auth_test_state(state)

        assert response.status_code == 200
        assert response.json() == {
            "username": "ivan",
            "role": "pto_engineer",
            "org_id": "default",
        }

    asyncio.run(_run())


def test_login_returns_jwt(tmp_path: Path):
    """Login should return bearer token and role."""

    async def _run() -> None:
        state = _configure_auth_test_state(tmp_path)
        _apply_auth_test_state(state)
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                register_response = await _register_user(client, "admin", "ADMIN-XXX", "pass123")
                assert register_response.status_code == 200
                login_response = await client.post(
                    "/auth/login",
                    json={"username": "admin", "password": "pass123"},
                )
        finally:
            _restore_auth_test_state(state)

        assert login_response.status_code == 200
        payload = login_response.json()
        assert payload["token_type"] == "bearer"
        assert payload["access_token"]
        assert payload["expires_in"] == settings.jwt_expire_minutes * 60
        assert payload["role"] == "admin"

    asyncio.run(_run())


def test_canonical_me_requires_token(tmp_path: Path):
    """GET /api/me should return 401 without any auth credentials."""

    async def _run() -> None:
        state = _configure_auth_test_state(tmp_path)
        _apply_auth_test_state(state)
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/api/me")
        finally:
            _restore_auth_test_state(state)
        assert response.status_code == 401

    asyncio.run(_run())


def test_canonical_me_rejects_invalid_jwt(tmp_path: Path):
    """GET /api/me should return 401 for invalid JWT in Authorization header."""

    async def _run() -> None:
        state = _configure_auth_test_state(tmp_path)
        _apply_auth_test_state(state)
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/api/me", headers={"Authorization": "Bearer invalid.jwt"})
        finally:
            _restore_auth_test_state(state)
        assert response.status_code == 401
        assert response.json() == {"detail": "Invalid token"}

    asyncio.run(_run())


def test_canonical_me_returns_profile_for_valid_jwt(tmp_path: Path):
    """GET /api/me should return stable profile contract for valid JWT."""

    async def _run() -> None:
        state = _configure_auth_test_state(tmp_path)
        _apply_auth_test_state(state)
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                register_response = await _register_user(client, "ivan", "PTO-XXX", "pass123")
                assert register_response.status_code == 200
                login_response = await client.post(
                    "/auth/login",
                    json={"username": "ivan", "password": "pass123"},
                )
                token = login_response.json()["access_token"]
                response = await client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
        finally:
            _restore_auth_test_state(state)

        assert response.status_code == 200
        assert response.json() == {
            "username": "ivan",
            "role": "pto_engineer",
            "org_id": "default",
            "is_admin": False,
        }

    asyncio.run(_run())


def test_canonical_me_returns_profile_for_valid_api_key(tmp_path: Path):
    """GET /api/me should return stable profile contract for valid X-API-Key."""

    async def _run() -> None:
        state = _configure_auth_test_state(tmp_path)
        _apply_auth_test_state(state)
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                register_response = await _register_user(client, "operator", "ADMIN-XXX", "pass123")
                assert register_response.status_code == 200
                with sqlite3.connect(settings.users_db_path) as connection:
                    connection.execute(
                        """
                        CREATE TABLE IF NOT EXISTS api_keys (
                            api_key TEXT PRIMARY KEY,
                            user_id TEXT NOT NULL
                        )
                        """
                    )
                    connection.execute(
                        "INSERT INTO api_keys (api_key, user_id) VALUES (?, ?)",
                        ("test-api-key-123456", "operator"),
                    )
                    connection.commit()
                response = await client.get(
                    "/api/me",
                    headers={"X-API-Key": "test-api-key-123456"},
                )
        finally:
            _restore_auth_test_state(state)

        assert response.status_code == 200
        assert response.json() == {
            "username": "operator",
            "role": "admin",
            "org_id": "default",
            "is_admin": True,
        }

    asyncio.run(_run())
