"""Tests for JWT auth routes."""

import asyncio
from pathlib import Path

from httpx import ASGITransport, AsyncClient

from api.main import app
from config.settings import settings


def test_register_with_valid_invite_code(tmp_path: Path):
    """Register endpoint should create user with mapped role."""

    async def _run() -> None:
        old_users_db_path = settings.users_db_path
        old_invite_codes = settings.invite_codes
        settings.users_db_path = str(tmp_path / "users.db")
        settings.invite_codes = {"PTO-XXX": "pto_engineer"}
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/auth/register",
                    json={
                        "username": "ivan",
                        "password": "pass123",
                        "invite_code": "PTO-XXX",
                    },
                )
        finally:
            settings.users_db_path = old_users_db_path
            settings.invite_codes = old_invite_codes

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
        old_users_db_path = settings.users_db_path
        old_invite_codes = settings.invite_codes
        old_jwt_secret = settings.jwt_secret
        settings.users_db_path = str(tmp_path / "users.db")
        settings.invite_codes = {"ADMIN-XXX": "admin"}
        settings.jwt_secret = "test-secret"
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                register_response = await client.post(
                    "/auth/register",
                    json={
                        "username": "admin",
                        "password": "pass123",
                        "invite_code": "ADMIN-XXX",
                    },
                )
                assert register_response.status_code == 200
                login_response = await client.post(
                    "/auth/login",
                    json={"username": "admin", "password": "pass123"},
                )
        finally:
            settings.users_db_path = old_users_db_path
            settings.invite_codes = old_invite_codes
            settings.jwt_secret = old_jwt_secret

        assert login_response.status_code == 200
        payload = login_response.json()
        assert payload["token_type"] == "bearer"
        assert payload["access_token"]
        assert payload["expires_in"] == settings.jwt_expire_minutes * 60
        assert payload["role"] == "admin"

    asyncio.run(_run())


def test_me_requires_auth():
    """Me endpoint should require auth token."""

    async def _run() -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/auth/me")
        assert response.status_code == 401
        assert response.json() == {"detail": "Invalid API key"}

    asyncio.run(_run())
