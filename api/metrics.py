from prometheus_client import Counter, Gauge, Histogram
from prometheus_fastapi_instrumentator import Instrumentator

# Кастомные метрики:
AGENT_RUNS = Counter(
    "construction_ai_agent_runs_total",
    "Количество запусков агентов",
    ["agent_id", "status"],  # status: success/error
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
    ["provider", "direction"],  # direction: input/output
)

__all__ = [
    "Instrumentator",
    "AGENT_RUNS",
    "PIPELINE_DURATION",
    "ACTIVE_SESSIONS",
    "LLM_TOKENS_USED",
]
