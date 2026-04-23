from prometheus_client import Counter, Gauge, Histogram
from prometheus_fastapi_instrumentator import Instrumentator

# Кастомные метрики:
AGENT_RUNS = Counter(
    "construction_ai_agent_runs_total",
    "Количество запусков агентов",
    ["agent_id", "status"],
)
PIPELINE_DURATION = Histogram(
    "construction_ai_pipeline_duration_seconds",
    "Время выполнения pipeline",
    ["intent"],
    buckets=[1, 5, 10, 30, 60, 120],
)
ACTIVE_SESSIONS = Gauge(
    "construction_ai_active_sessions",
    "Количество активных сессий",
)
LLM_TOKENS_USED = Counter(
    "construction_ai_llm_tokens_total",
    "Использовано LLM токенов",
    ["provider", "direction"],
)
BOT_MESSAGES_TOTAL = Counter(
    "bot_messages_total",
    "Количество обработанных сообщений Telegram-ботом",
    ["handler"],
)

RESEARCHER_REQUESTS_TOTAL = Counter(
    "researcher_requests_total",
    "Researcher request count",
    ["status"],
)
RESEARCHER_LLM_DURATION_SECONDS = Histogram(
    "researcher_llm_duration_seconds",
    "Researcher LLM call duration",
)
RESEARCHER_CACHE_HITS_TOTAL = Counter(
    "researcher_cache_hits_total",
    "Researcher cache hits",
)
RESEARCHER_WEB_FALLBACK_TOTAL = Counter(
    "researcher_web_fallback_total",
    "Researcher web fallback count",
)
RESEARCHER_SOURCES_COUNT = Histogram(
    "researcher_sources_count",
    "Researcher source count per request",
)
RESEARCHER_INJECTION_DETECTED_TOTAL = Counter(
    "researcher_injection_detected_total",
    "Researcher injection detections",
)

__all__ = [
    "Instrumentator",
    "AGENT_RUNS",
    "PIPELINE_DURATION",
    "ACTIVE_SESSIONS",
    "LLM_TOKENS_USED",
    "BOT_MESSAGES_TOTAL",
    "RESEARCHER_REQUESTS_TOTAL",
    "RESEARCHER_LLM_DURATION_SECONDS",
    "RESEARCHER_CACHE_HITS_TOTAL",
    "RESEARCHER_WEB_FALLBACK_TOTAL",
    "RESEARCHER_SOURCES_COUNT",
    "RESEARCHER_INJECTION_DETECTED_TOTAL",
]
