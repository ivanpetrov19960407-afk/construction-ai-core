"""Настройки приложения — загружаются из .env."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Глобальные настройки Construction AI Core."""

    # ── API ────────────────────────────────────
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    debug: bool = True

    # ── LLM Providers ──────────────────────────
    perplexity_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    deepseek_api_key: str = ""
    default_llm_provider: str = "perplexity"

    # ── Database ───────────────────────────────
    database_url: str = "sqlite:///./data/construction_ai.db"

    # ── ChromaDB ───────────────────────────────
    chroma_persist_dir: str = "./data/chroma"

    # ── Redis (серверный деплой) ────────────────
    redis_url: str | None = None

    # ── Telegram ───────────────────────────────
    telegram_bot_token: str = ""

    # ── tk-generator ───────────────────────────
    tk_generator_path: str = "../tk-generator"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
