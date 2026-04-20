"""Reusable API dependencies."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from fastapi import Header, HTTPException, Request

from api.security import JWTError, decode_jwt
from config.settings import settings


@dataclass(frozen=True)
class CurrentUser:
    username: str
    role: str
    org_id: str = "default"


def _ensure_api_keys_table() -> None:
    db_path = Path(settings.users_db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS api_keys (
                api_key TEXT PRIMARY KEY,
                user_id TEXT NOT NULL
            )
            """
        )
        connection.commit()


def _lookup_api_key_user(api_key: str) -> str | None:
    _ensure_api_keys_table()
    with sqlite3.connect(settings.users_db_path) as connection:
        row = connection.execute(
            "SELECT user_id FROM api_keys WHERE api_key = ?",
            (api_key,),
        ).fetchone()
    if row is None:
        return None
    return str(row[0])


def _decode_jwt_token(token: str) -> dict[str, str]:
    try:
        payload = decode_jwt(token, settings.jwt_secret, algorithms=["HS256"])
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    username = payload.get("sub")
    role = payload.get("role")
    org_id = payload.get("org_id")
    if not username or not role:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    return {"username": str(username), "role": str(role), "org_id": str(org_id or "default")}


async def current_user(
    request: Request,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> CurrentUser:
    """Resolve authenticated user from JWT first, then API key mapping."""
    if authorization and authorization.startswith("Bearer "):
        payload = _decode_jwt_token(authorization.removeprefix("Bearer ").strip())
        return CurrentUser(
            username=payload["username"],
            role=payload["role"],
            org_id=payload.get("org_id", "default"),
        )

    if x_api_key:
        if x_api_key not in settings.api_keys:
            raise HTTPException(status_code=401, detail="Authentication required")
        username = _lookup_api_key_user(x_api_key)
        role = "admin" if x_api_key in settings.admin_api_keys else "pto_engineer"
        if username:
            return CurrentUser(username=username, role=role, org_id="default")
        return CurrentUser(username=f"api_key:{x_api_key[-6:]}", role=role, org_id="default")

    state_username = getattr(request.state, "username", None)
    state_role = getattr(request.state, "user_role", None)
    if state_username and state_role:
        return CurrentUser(
            username=str(state_username),
            role=str(state_role),
            org_id=str(getattr(request.state, "org_id", "default") or "default"),
        )

    raise HTTPException(status_code=401, detail="Authentication required")
