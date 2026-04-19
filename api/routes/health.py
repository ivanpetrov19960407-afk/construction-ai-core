"""Health-check endpoint."""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request

from config.settings import settings
from core.database import get_db, init_db
from core.llm_router import LLMProvider
from core.rag_engine import RAGEngine

router = APIRouter()

LLM_PROVIDER_TO_SETTING = {
    "perplexity": "perplexity_api_key",
    "openai": "openai_api_key",
    "claude": "anthropic_api_key",
    "gigachat": "gigachat_credentials",
    "yandexgpt": "yandexgpt_api_key",
    "deepseek": "deepseek_api_key",
}


def _check_llm_router() -> dict[str, object]:
    provider_name = settings.default_llm_provider
    available = settings.configured_llm_providers
    missing_keys = [name for name in LLM_PROVIDER_TO_SETTING if name not in available]

    try:
        _ = LLMProvider(provider_name)
        default_supported = True
    except Exception:
        default_supported = False

    default_configured = provider_name in available
    is_degraded = not default_supported or not default_configured

    status = "ok"
    if is_degraded:
        status = "degraded" if default_supported else "error"

    check: dict[str, object] = {
        "status": status,
        "provider": provider_name,
        "default_supported": default_supported,
        "default_configured": default_configured,
        "available_providers": available,
        "missing_keys": missing_keys,
    }
    if not default_supported:
        check["reason"] = "unsupported_default_provider"
    elif not default_configured:
        check["reason"] = "missing_default_provider_key"

    return check


@router.get("/health")
async def health_check(request: Request):
    """Проверка состояния сервиса."""
    components: dict[str, dict[str, Any]] = {}

    # database
    db_status = "ok"
    sessions_count = 0
    try:
        await init_db(settings.sqlite_db_path)
        async with get_db(settings.sqlite_db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) AS total FROM sessions")
            row = await cursor.fetchone()
            sessions_count = int(row["total"]) if row else 0
    except Exception:
        db_status = "error"
    components["database"] = {
        "status": db_status,
        "sessions_count": sessions_count,
    }

    # rag engine
    rag_status = "ok"
    chunks_count = 0
    rag_sources_count = 0
    try:
        rag_stats = RAGEngine().get_stats()
        chunks_count = int(rag_stats.get("total_chunks", 0))
        rag_sources_count = len(rag_stats.get("sources", []))
    except Exception:
        rag_status = "error"
    components["rag_engine"] = {
        "status": rag_status,
        "chunks_count": chunks_count,
        "sources": rag_sources_count,
    }

    # llm router
    llm_check = _check_llm_router()
    components["llm_router"] = llm_check

    # telegram webhook
    telegram_configured = bool(settings.telegram_webhook_url and settings.bot_token)
    telegram_active = bool(
        settings.telegram_webhook_url
        and settings.bot_token
        and getattr(request.app.state, "telegram_bot", None) is not None
        and getattr(request.app.state, "telegram_dp", None) is not None
    )
    components["telegram_webhook"] = {
        "status": "active" if telegram_active else "inactive",
    }

    service_status = "ok"
    if components["database"]["status"] == "error" or llm_check["status"] == "error":
        service_status = "error"
    elif (
        rag_status == "error"
        or llm_check["status"] == "degraded"
        or (telegram_configured and components["telegram_webhook"]["status"] == "inactive")
    ):
        service_status = "degraded"

    started_at = getattr(request.app.state, "started_at", None)
    uptime_seconds = 0.0
    if started_at is not None:
        now = datetime.now(timezone.utc)  # noqa: UP017
        uptime_seconds = max(0.0, (now - started_at).total_seconds())

    llm = {
        "default": settings.default_llm_provider,
        "available": settings.configured_llm_providers,
        "degraded": bool(llm_check["status"] != "ok"),
    }

    return {
        "status": service_status,
        "service": "construction-ai-core",
        "version": "0.1.0",
        "uptime_seconds": round(uptime_seconds, 1),
        "checks": components,
        "components": components,
        "llm": llm,
    }
