"""Construction AI Core — FastAPI application."""

import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from hmac import compare_digest
from typing import cast

from aiogram.types import Update
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded

from api.metrics import AGENT_RUNS, PIPELINE_DURATION, Instrumentator
from api.middleware import (
    APIKeyMiddleware,
    RequestLoggingMiddleware,
    SlowAPIMiddleware,
    configure_structlog,
    limiter,
    rate_limit_exceeded_handler,
    setup_rate_limiter,
)
from api.routes import (
    analytics,
    auth,
    billing,
    branding,
    chat,
    compliance,
    generate,
    health,
    isup,
    linking,
    projects,
    rag,
    sign,
    web,
    web_push,
)
from api.routes.analyze import router as analyze_router
from config.settings import settings
from core.analytics.notifications import AnalyticsNotifier
from core.database import init_db
from telegram.main import create_bot, create_dispatcher

_ = (AGENT_RUNS, PIPELINE_DURATION)
telegram_router = APIRouter()
analytics_notifier = AnalyticsNotifier()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown events."""
    configure_structlog()
    settings.validate_jwt_secret()
    await init_db(settings.sqlite_db_path)
    app.state.started_at = datetime.now(timezone.utc)  # noqa: UP017
    app.state.telegram_bot = None
    app.state.telegram_dp = None
    await analytics_notifier.start()
    if settings.telegram_webhook_url and settings.bot_token:
        app.state.telegram_bot = create_bot()
        app.state.telegram_dp = create_dispatcher()
        if settings.telegram_webhook_secret:
            await app.state.telegram_bot.set_webhook(
                settings.telegram_webhook_url,
                secret_token=settings.telegram_webhook_secret,
            )
        else:
            await app.state.telegram_bot.set_webhook(settings.telegram_webhook_url)
    print("🚀 Construction AI Core запускается...")
    yield
    await analytics_notifier.stop()
    if app.state.telegram_bot is not None:
        await app.state.telegram_bot.delete_webhook(drop_pending_updates=False)
        await app.state.telegram_bot.session.close()
    print("🛑 Construction AI Core останавливается...")


app = FastAPI(
    title="Construction AI Core",
    description=(
        "Универсальный ИИ-помощник для строительной отрасли "
        "(генерация документов и анализ PDF-документации)"
    ),
    version="0.1.0",
    lifespan=lifespan,
)

Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# CORS — для Tauri и Web UI
cors_origins = list(settings.cors_origins)
has_wildcard_origin = "*" in cors_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if has_wildcard_origin else cors_origins,
    allow_credentials=not has_wildcard_origin,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(APIKeyMiddleware)
app.state.limiter = limiter


def _rate_limit_handler(request: Request, exc: Exception) -> Response:
    return rate_limit_exceeded_handler(request, cast(RateLimitExceeded, exc))


app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)

# ── Routes ─────────────────────────────────────
app.include_router(health.router, tags=["health"])
app.include_router(auth.router, tags=["auth"])
app.include_router(auth.api_router, tags=["auth"])
app.include_router(billing.router, prefix="/api", tags=["billing"])
app.include_router(branding.router, prefix="/api", tags=["branding"])
app.include_router(chat.router, prefix="/api", tags=["chat"])
# generate.router содержит /api/generate/* включая /api/generate/exec-album
app.include_router(generate.router, prefix="/api", tags=["generate"])
app.include_router(sign.router, prefix="/api", tags=["sign"])
app.include_router(isup.router)
app.include_router(analyze_router, prefix="/api/analyze", tags=["analyze"])
app.include_router(rag.router, prefix="/api/rag", tags=["rag"])
app.include_router(projects.router, prefix="/api", tags=["projects"])
app.include_router(analytics.router, prefix="/api", tags=["analytics"])
app.include_router(compliance.router, prefix="/api", tags=["compliance"])
app.include_router(linking.router, prefix="/api", tags=["linking"])
app.include_router(linking.notifications_router, prefix="/api", tags=["notifications"])
app.include_router(web_push.router)
app.include_router(web.router, tags=["web"])
app.mount("/web", StaticFiles(directory="web", html=True), name="web")
setup_rate_limiter(app.routes)


@telegram_router.post(
    "/telegram/webhook",
    summary="Webhook Telegram",
    description=(
        "Принимает входящие обновления от Telegram Bot API и передаёт их в диспетчер aiogram."
    ),
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "example": {
                        "update_id": 123456789,
                        "message": {
                            "message_id": 101,
                            "date": 1735689600,
                            "chat": {"id": 123456789, "type": "private"},
                            "text": "/start",
                        },
                    }
                }
            },
        }
    },
)
async def telegram_webhook_handler(request: Request) -> dict[str, bool]:
    bot = request.app.state.telegram_bot
    dp = request.app.state.telegram_dp
    if bot is None or dp is None:
        raise HTTPException(status_code=503, detail="Telegram webhook is not configured")
    if not settings.telegram_webhook_secret:
        raise HTTPException(
            status_code=503,
            detail="Telegram webhook secret is not configured",
        )

    received_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not compare_digest(received_secret, settings.telegram_webhook_secret):
        raise HTTPException(status_code=403, detail="Invalid Telegram webhook secret")

    payload = await request.json()
    update = Update.model_validate(payload, context={"bot": bot})
    await dp.feed_update(bot, update)
    return {"ok": True}


@telegram_router.get("/api/telegram/health")
async def telegram_health() -> dict[str, int]:
    active_sessions = 0
    try:
        with sqlite3.connect(settings.sqlite_db_path) as connection:
            row = connection.execute("SELECT COUNT(*) FROM sessions").fetchone()
            active_sessions = int(row[0]) if row else 0
    except sqlite3.Error:
        active_sessions = 0
    return {"active_sessions": active_sessions}


app.include_router(telegram_router, tags=["telegram"])
