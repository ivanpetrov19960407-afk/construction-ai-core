"""LLM Router — маршрутизация запросов к нужному LLM-провайдеру.

Позволяет менять провайдера без изменения бизнес-логики.
Поддерживаемые провайдеры: Perplexity, OpenAI, Claude, Deepseek.
"""

from dataclasses import dataclass
from enum import Enum

import httpx

from api.metrics import LLM_TOKENS_USED
from config.settings import settings


class LLMProvider(str, Enum):  # noqa: UP042
    """Доступные LLM-провайдеры."""

    PERPLEXITY = "perplexity"
    OPENAI = "openai"
    CLAUDE = "claude"
    DEEPSEEK = "deepseek"


@dataclass
class LLMResponse:
    """Унифицированный ответ от любого LLM."""

    text: str
    provider: LLMProvider
    model: str
    usage: dict | None = None


# ── Конфигурация провайдеров ───────────────────

PROVIDER_CONFIG = {
    LLMProvider.PERPLEXITY: {
        "base_url": "https://api.perplexity.ai",
        "default_model": "sonar",
        "api_key_field": "perplexity_api_key",
    },
    LLMProvider.OPENAI: {
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o",
        "api_key_field": "openai_api_key",
    },
    LLMProvider.CLAUDE: {
        "base_url": "https://api.anthropic.com/v1",
        "default_model": "claude-sonnet-4-20250514",
        "api_key_field": "anthropic_api_key",
    },
    LLMProvider.DEEPSEEK: {
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
        "api_key_field": "deepseek_api_key",
    },
}


class LLMRouter:
    """Единый класс для маршрутизации запросов к LLM.

    Usage:
        router = LLMRouter()
        response = await router.query("Расскажи о СП 48.13330")
        response = await router.query("...", provider=LLMProvider.OPENAI)
    """

    def __init__(self, default_provider: LLMProvider | None = None):
        self.default_provider = default_provider or LLMProvider(settings.default_llm_provider)
        self._client = httpx.AsyncClient(timeout=60.0)

    async def query(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        provider: LLMProvider | None = None,
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Отправить запрос к LLM-провайдеру.

        Args:
            prompt: Текст запроса пользователя.
            system_prompt: Системный промпт (роль агента).
            provider: Конкретный провайдер (по умолчанию — из настроек).
            model: Модель (по умолчанию — default_model провайдера).
            temperature: Температура генерации.
            max_tokens: Максимальное количество токенов.

        Returns:
            LLMResponse с текстом ответа и метаданными.
        """
        provider = provider or self.default_provider
        config = PROVIDER_CONFIG[provider]
        model = model or config["default_model"]
        api_key = getattr(settings, config["api_key_field"])

        if not api_key:
            raise ValueError(
                f"API-ключ для {provider.value} не настроен. "
                f"Добавьте {config['api_key_field'].upper()} в .env"
            )

        # Формируем messages
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # Отправляем запрос (OpenAI-совместимый формат)
        if provider == LLMProvider.CLAUDE:
            response_data = await self._query_claude(
                api_key, model, messages, temperature, max_tokens
            )
        else:
            response_data = await self._query_openai_compatible(
                config["base_url"], api_key, model, messages, temperature, max_tokens
            )

        usage = response_data.get("usage") or {}
        if isinstance(usage, dict) and "prompt_tokens" in usage:
            LLM_TOKENS_USED.labels(provider=provider.value, direction="input").inc(
                usage["prompt_tokens"]
            )

        return LLMResponse(
            text=response_data["text"],
            provider=provider,
            model=model,
            usage=response_data.get("usage"),
        )

    async def _query_openai_compatible(
        self,
        base_url: str,
        api_key: str,
        model: str,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
    ) -> dict:
        """Запрос через OpenAI-совместимый API (Perplexity, OpenAI, Deepseek)."""
        response = await self._client.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )
        response.raise_for_status()
        data = response.json()
        return {
            "text": data["choices"][0]["message"]["content"],
            "usage": data.get("usage"),
        }

    async def _query_claude(
        self,
        api_key: str,
        model: str,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
    ) -> dict:
        """Запрос через Anthropic API (отличается от OpenAI формата)."""
        # Разделяем system и user messages
        system_text = ""
        user_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_text = msg["content"]
            else:
                user_messages.append(msg)

        body: dict = {
            "model": model,
            "messages": user_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if system_text:
            body["system"] = system_text

        response = await self._client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=body,
        )
        response.raise_for_status()
        data = response.json()
        return {
            "text": data["content"][0]["text"],
            "usage": data.get("usage"),
        }

    async def close(self):
        """Закрыть HTTP-клиент."""
        await self._client.aclose()
