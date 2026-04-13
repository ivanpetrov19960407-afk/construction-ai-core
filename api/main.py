"""Construction AI Core — FastAPI application."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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
from api.routes import chat, generate, health
from config.settings import settings
from core.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown events."""
    configure_structlog()
    await init_db(settings.sqlite_db_path)
    print("🚀 Construction AI Core запускается...")
    yield
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
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# ── Routes ─────────────────────────────────────
app.include_router(health.router, tags=["health"])
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(generate.router, prefix="/api", tags=["generate"])
setup_rate_limiter(app.routes)
