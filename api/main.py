"""Construction AI Core — FastAPI application."""

from contextlib import asynccontextmanager
from typing import cast

from aiogram.types import Update
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from slowapi.errors import RateLimitExceeded

from api.middleware import (
    APIKeyMiddleware,
    RequestLoggingMiddleware,
    SlowAPIMiddleware,
    configure_structlog,
    limiter,
    rate_limit_exceeded_handler,
    setup_rate_limiter,
)
from api.routes import chat, generate, health, rag
from api.routes.analyze import router as analyze_router
from config.settings import settings
from core.database import init_db
from telegram.bot import create_bot, create_dispatcher

telegram_router = APIRouter()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown events."""
    configure_structlog()
    await init_db(settings.sqlite_db_path)
    app.state.telegram_bot = None
    app.state.telegram_dp = None
    if settings.telegram_webhook_url and settings.bot_token:
        app.state.telegram_bot = create_bot()
        app.state.telegram_dp = create_dispatcher()
        await app.state.telegram_bot.set_webhook(settings.telegram_webhook_url)
    print("🚀 Construction AI Core запускается...")
    yield
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

# CORS — для Tauri и Web UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: ограничить в production
    allow_credentials=True,
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
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(generate.router, prefix="/api", tags=["generate"])
app.include_router(analyze_router, prefix="/api/analyze", tags=["analyze"])
app.include_router(rag.router, prefix="/api/rag", tags=["rag"])
setup_rate_limiter(app.routes)


@telegram_router.post("/telegram/webhook")
async def telegram_webhook_handler(request: Request) -> dict[str, bool]:
    bot = request.app.state.telegram_bot
    dp = request.app.state.telegram_dp
    if bot is None or dp is None:
        raise HTTPException(status_code=503, detail="Telegram webhook is not configured")

    payload = await request.json()
    update = Update.model_validate(payload, context={"bot": bot})
    await dp.feed_update(bot, update)
    return {"ok": True}


app.include_router(telegram_router, tags=["telegram"])
