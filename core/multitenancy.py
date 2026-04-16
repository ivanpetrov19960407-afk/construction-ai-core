"""Helpers and middleware for org_id-based multitenancy."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Request

from api.security import JWTError, decode_jwt
from config.settings import settings

ALGORITHM = "HS256"


async def get_tenant_id(request: Request) -> str | None:
    """Получить org_id из JWT-payload или X-Org-Id header."""
    _ = getattr(request.state, "user_role", None)
    org_id = getattr(request.state, "org_id", None)
    if org_id:
        return str(org_id)

    header_org_id = request.headers.get("X-Org-Id")
    if header_org_id:
        return header_org_id

    return None


class TenantMiddleware:
    """Middleware: извлечь org_id из JWT и сохранить в request.state.org_id."""

    def __init__(self, app: Callable[..., Awaitable[Any]]) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") == "http":
            state = scope.setdefault("state", {})
            org_id = None

            headers = {
                key.decode("latin-1").lower(): value.decode("latin-1")
                for key, value in scope.get("headers", [])
            }
            auth_header = headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header.removeprefix("Bearer ").strip()
                try:
                    payload = decode_jwt(token, settings.jwt_secret, algorithms=[ALGORITHM])
                except JWTError:
                    payload = {}
                org_claim = payload.get("org_id")
                if org_claim:
                    org_id = str(org_claim)

            org_id = org_id or headers.get("x-org-id")
            if org_id:
                state["org_id"] = org_id

        await self.app(scope, receive, send)
