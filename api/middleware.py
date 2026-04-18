"""Middleware and infrastructure for API security, rate limits and logging."""

from __future__ import annotations

import json
import logging
import time
import traceback
from collections.abc import Awaitable, Callable
from typing import Any, cast

import structlog
from fastapi import Request
from fastapi.responses import JSONResponse, Response
from fastapi.routing import APIRoute
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.routing import BaseRoute

from api.routes.auth import decode_jwt_token
from config.settings import settings

<<<<<<< Updated upstream
EXCLUDED_PATHS = {"/health", "/docs", "/redoc", "/openapi.json", "/telegram/webhook", "/metrics"}
PUBLIC_AUTH_PATHS = {"/auth/register", "/auth/login"}
=======
EXCLUDED_PATHS = {"/health", "/docs", "/redoc", "/openapi.json", "/webhook", "/telegram/webhook", "/metrics", "/api/chat"}
>>>>>>> Stashed changes
limiter = Limiter(key_func=get_remote_address, default_limits=[])


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Security middleware supporting JWT bearer and legacy X-API-Key."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        path = request.url.path
        if (
            path in EXCLUDED_PATHS
            or path in PUBLIC_AUTH_PATHS
            or path == "/web"
            or path.startswith("/web/")
        ):
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.removeprefix("Bearer ").strip()
            payload = decode_jwt_token(token)
            request.state.username = payload["username"]
            request.state.user_role = payload["role"]
            request.state.org_id = payload.get("org_id", "default")
            return await call_next(request)

        provided_key = request.headers.get("X-API-Key")
        if provided_key not in settings.api_keys:
            return JSONResponse(status_code=401, content={"detail": "Invalid API key"})
        return await call_next(request)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Structured logging for every incoming request."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        started = time.perf_counter()
        logger = structlog.get_logger("api.requests")
        session_id = request.headers.get("X-Session-ID") or request.query_params.get("session_id")
        traceback_text: str | None = None

        if session_id is None:
            body = await request.body()
            if body:
                try:
                    payload = json.loads(body.decode("utf-8"))
                    if isinstance(payload, dict):
                        session_id = payload.get("session_id")
                except (ValueError, UnicodeDecodeError):
                    session_id = None

            async def _receive() -> dict[str, object]:
                return {"type": "http.request", "body": body, "more_body": False}

            request._receive = _receive  # type: ignore[attr-defined]

        try:
            response = await call_next(request)
        except Exception:
            traceback_text = traceback.format_exc()
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            logger.exception(
                "request_failed",
                method=request.method,
                path=request.url.path,
                status_code=500,
                duration_ms=duration_ms,
                session_id=session_id,
                traceback=traceback_text,
            )
            raise

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            "request_finished",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            session_id=session_id,
        )
        return response


def configure_structlog() -> None:
    """Initialize stdlib logging and structlog processors."""
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(message)s",
    )
    if settings.debug:
        processors: list[Any] = [
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.dev.ConsoleRenderer(colors=True),
        ]
    else:
        processors = [
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ]

    structlog.configure(
        processors=processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Custom 429 body for exceeded limits."""
    return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})


def setup_rate_limiter(app_routes: list[BaseRoute]) -> None:
    """Attach per-route limits according to project rules."""
    for route in app_routes:
        if not isinstance(route, APIRoute):
            continue
        path = getattr(route, "path", "")
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None:
            continue

        if path == "/api/chat":
            route.endpoint = cast(Any, limiter.limit("60/minute")(endpoint))
        elif path.startswith("/api/generate/"):
            route.endpoint = cast(Any, limiter.limit("10/minute")(endpoint))
        elif path.startswith("/api/analyze/"):
            route.endpoint = cast(Any, limiter.limit("5/minute")(endpoint))


__all__ = [
    "APIKeyMiddleware",
    "RequestLoggingMiddleware",
    "SlowAPIMiddleware",
    "configure_structlog",
    "limiter",
    "rate_limit_exceeded_handler",
    "setup_rate_limiter",
]
