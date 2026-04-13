"""Construction AI Core — FastAPI application."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import chat, generate, health
from config.settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown events."""
    # TODO: инициализация ChromaDB, загрузка orchestrator.json
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

# ── Routes ─────────────────────────────────────
app.include_router(health.router, tags=["health"])
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(generate.router, prefix="/api", tags=["generate"])
