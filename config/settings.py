"""Настройки приложения — загружаются из .env."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Глобальные настройки Construction AI Core."""

    # ── API ────────────────────────────────────
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    debug: bool = False
    log_level: str = "INFO"
    api_keys: list[str] = []
    admin_api_keys: list[str] = []
    jwt_secret: str = "changeme"
    jwt_expire_minutes: int = 60
    users_db_path: str = "data/users.db"
    invite_codes: dict[str, str] = {
        "ADMIN-XXX": "admin",
        "PTO-XXX": "pto_engineer",
        "FOREMAN-XXX": "foreman",
        "TENDER-XXX": "tender_specialist",
    }

    # ── LLM Providers ──────────────────────────
    perplexity_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    deepseek_api_key: str = ""
    default_llm_provider: str = "perplexity"

    # ── Database ───────────────────────────────
    database_url: str = "sqlite:///./data/construction_ai.db"
    sqlite_db_path: str = "./data/construction_ai.db"

    # ── ChromaDB ───────────────────────────────
    chroma_persist_dir: str = "./data/chroma"

    # ── RAG ────────────────────────────────────
    rag_embeddings_backend: str = "sentence_transformers"

    # ── Redis (серверный деплой) ────────────────
    redis_url: str = "redis://redis:6379"

    # ── Telegram ───────────────────────────────
    bot_token: str = ""
    core_api_url: str = "http://api:8000"
    telegram_bot_token: str = ""
    telegram_webhook_url: str = ""
    admin_telegram_ids: list[int] = []

    # ── tk-generator ───────────────────────────
    tk_generator_path: str = "../tk-generator"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    def validate_jwt_secret(self) -> None:
        """Ensure JWT secret is explicitly configured and strong enough."""
        normalized = self.jwt_secret.strip().lower()
        insecure_values = {"", "changeme", "change-me", "default", "secret"}
        if normalized in insecure_values or len(self.jwt_secret) < 32:
            raise ValueError(
                "Unsafe JWT secret: set JWT_SECRET to a unique value with at least 32 chars",
            )


settings = Settings()
