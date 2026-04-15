"""Authentication routes with invite-based registration and JWT."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from jose import JWTError, jwt
from passlib.context import CryptContext

from api.models import TokenResponse, UserCreate, UserLogin
from config.settings import settings

ALGORITHM = "HS256"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
router = APIRouter(prefix="/auth", tags=["auth"])


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
                created_at TEXT NOT NULL
            )
            """
        )
        connection.commit()


def _get_user(username: str) -> tuple[str, str, str, str] | None:
    _ensure_users_table()
    with sqlite3.connect(settings.users_db_path) as connection:
        cursor = connection.execute(
            "SELECT username, password_hash, role, created_at FROM users WHERE username = ?",
            (username,),
        )
        row = cursor.fetchone()
    if row is None:
        return None
    return (str(row[0]), str(row[1]), str(row[2]), str(row[3]))


def _create_token(username: str, role: str) -> str:
    expire_at = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {
        "sub": username,
        "role": role,
        "exp": int(expire_at.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


@router.post("/register")
async def register_user(payload: UserCreate) -> dict[str, str]:
    """Register user using invite code mapped to a role."""
    role = settings.invite_codes.get(payload.invite_code)
    if role is None:
        raise HTTPException(status_code=403, detail="Invalid invite code")

    if _get_user(payload.username) is not None:
        raise HTTPException(status_code=409, detail="User already exists")

    _ensure_users_table()
    created_at = datetime.now(timezone.utc).isoformat()
    password_hash = pwd_context.hash(payload.password)
    with sqlite3.connect(settings.users_db_path) as connection:
        connection.execute(
            """
            INSERT INTO users (username, password_hash, role, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (payload.username, password_hash, role, created_at),
        )
        connection.commit()
    return {"username": payload.username, "role": role}


@router.post("/login", response_model=TokenResponse)
async def login_user(payload: UserLogin) -> TokenResponse:
    """Authenticate user and return bearer JWT."""
    user = _get_user(payload.username)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    username, password_hash, role, _created_at = user
    if not pwd_context.verify(payload.password, password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    return TokenResponse(
        access_token=_create_token(username, role),
        token_type="bearer",
        expires_in=settings.jwt_expire_minutes * 60,
        role=role,
    )


@router.get("/me")
async def me(request: Request) -> dict[str, str]:
    """Return current user profile based on middleware-populated JWT context."""
    username = getattr(request.state, "username", None)
    user_role = getattr(request.state, "user_role", None)
    if username is None or user_role is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    user = _get_user(username)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    _username, _password_hash, role, created_at = user
    return {"username": username, "role": role, "created_at": created_at}


def decode_jwt_token(token: str) -> dict[str, str]:
    """Decode JWT and return username/role payload."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    username = payload.get("sub")
    role = payload.get("role")
    if not username or not role:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    return {"username": str(username), "role": str(role)}
