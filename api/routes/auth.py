"""Authentication routes with invite-based registration and JWT."""

from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from api.models import TokenResponse, UserCreate, UserLogin
from api.security import JWTError, decode_jwt, encode_jwt, hash_password, verify_password
from config.settings import settings

ALGORITHM = "HS256"
UTC = getattr(dt, "UTC", dt.timezone.utc)  # noqa: UP017
router = APIRouter(prefix="/auth", tags=["auth"])
api_router = APIRouter(prefix="/api/auth", tags=["auth"])


def _ensure_users_table() -> None:
    db_path = Path(settings.users_db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                org_id TEXT NOT NULL DEFAULT 'default',
                created_at TEXT NOT NULL
            )
            """
        )
        columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(users)").fetchall()}
        if "org_id" not in columns:
            connection.execute(
                "ALTER TABLE users ADD COLUMN org_id TEXT NOT NULL DEFAULT 'default'"
            )
        connection.commit()


def _get_user(username: str) -> tuple[str, str, str, str, str] | None:
    _ensure_users_table()
    with sqlite3.connect(settings.users_db_path) as connection:
        cursor = connection.execute(
            (
                "SELECT username, password_hash, role, org_id, created_at "
                "FROM users WHERE username = ?"
            ),
            (username,),
        )
        row = cursor.fetchone()
    if row is None:
        return None
    return (str(row[0]), str(row[1]), str(row[2]), str(row[3]), str(row[4]))


def _create_token(username: str, role: str, org_id: str = "default") -> str:
    expire_at = dt.datetime.now(UTC) + dt.timedelta(minutes=settings.jwt_expire_minutes)
    payload = {
        "sub": username,
        "role": role,
        "org_id": org_id or "default",
        "exp": int(expire_at.timestamp()),
    }
    return encode_jwt(payload, settings.jwt_secret, algorithm=ALGORITHM)


async def _register_impl(payload: UserCreate) -> dict[str, str]:
    role = settings.invite_codes.get(payload.invite_code)
    if role is None:
        raise HTTPException(status_code=403, detail="Invalid invite code")

    if _get_user(payload.username) is not None:
        raise HTTPException(status_code=409, detail="User already exists")

    _ensure_users_table()
    created_at = dt.datetime.now(UTC).isoformat()
    password_hash = hash_password(payload.password)
    with sqlite3.connect(settings.users_db_path) as connection:
        connection.execute(
            """
            INSERT INTO users (username, password_hash, role, org_id, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (payload.username, password_hash, role, payload.org_id or "default", created_at),
        )
        connection.commit()
    return {"username": payload.username, "role": role, "org_id": payload.org_id or "default"}


async def _login_impl(payload: UserLogin) -> TokenResponse:
    user = _get_user(payload.username)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    username, password_hash, role, org_id, _created_at = user
    if not verify_password(payload.password, password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    return TokenResponse(
        access_token=_create_token(username, role, org_id),
        token_type="bearer",
        expires_in=settings.jwt_expire_minutes * 60,
        role=role,
    )


@router.post("/register")
async def register_user(payload: UserCreate) -> dict[str, str]:
    return await _register_impl(payload)


@router.post("/login", response_model=TokenResponse)
async def login_user(payload: UserLogin) -> TokenResponse:
    return await _login_impl(payload)


@api_router.post("/register")
async def api_register_user(payload: UserCreate) -> dict[str, str]:
    return await _register_impl(payload)


@api_router.post("/login", response_model=TokenResponse)
async def api_login_user(payload: UserLogin) -> TokenResponse:
    return await _login_impl(payload)


def _build_me_response(request: Request) -> dict[str, str | bool]:
    """Return current user profile based on middleware-populated JWT context."""
    username = getattr(request.state, "username", None)
    user_role = getattr(request.state, "user_role", None)
    if username is None or user_role is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    user = _get_user(username)
    if user is None:
        role = str(user_role)
        return {
            "username": username,
            "role": role,
            "org_id": "default",
            "is_admin": role == "admin",
        }

    _username, _password_hash, role, org_id, _created_at = user
    return {"username": username, "role": role, "org_id": org_id, "is_admin": role == "admin"}


@router.get("/me")
async def me(request: Request) -> dict[str, str | bool]:
    return _build_me_response(request)


@api_router.get("/me", include_in_schema=False)
async def api_auth_me(request: Request) -> dict[str, str | bool]:
    return _build_me_response(request)


def decode_jwt_token(token: str) -> dict[str, str]:
    """Decode JWT and return username/role payload."""
    try:
        payload = decode_jwt(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    username = payload.get("sub")
    role = payload.get("role")
    org_id = payload.get("org_id")
    if not username or not role:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    return {"username": str(username), "role": str(role), "org_id": str(org_id or "default")}
