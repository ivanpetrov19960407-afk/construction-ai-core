"""LLM Router — маршрутизация запросов к нужному LLM-провайдеру.

Позволяет менять провайдера без изменения бизнес-логики.
Поддерживаемые провайдеры: Perplexity, OpenAI, Claude, Deepseek.
"""

import asyncio
from collections import OrderedDict
from dataclasses import dataclass
from enum import Enum
import time

import httpx
import structlog

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
        self._logger = structlog.get_logger("core.llm_router")
        self._intent_cache: OrderedDict[int, tuple[str, float]] = OrderedDict()
        self._intent_cache_ttl_seconds = 3600
        self._intent_cache_max_entries = 1000

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
        providers_chain = [provider, *[p for p in LLMProvider if p != provider]]

        # Формируем messages
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        cache_key = self._intent_cache_key(system_prompt, prompt)
        if cache_key is not None:
            cached_intent = self._get_cached_intent(cache_key)
            if cached_intent is not None:
                return LLMResponse(
                    text=cached_intent,
                    provider=provider,
                    model=model or PROVIDER_CONFIG[provider]["default_model"],
                    usage={"tokens_input": 0, "tokens_output": 0},
                )

        response_data = None
        used_provider = None
        used_model = None
        max_attempts = 3
        last_error: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            current_provider = providers_chain[attempt - 1]
            config = PROVIDER_CONFIG[current_provider]
            current_model = model or config["default_model"]
            api_key = getattr(settings, config["api_key_field"])
            if not api_key:
                last_error = ValueError(
                    f"API-ключ для {current_provider.value} не настроен. "
                    f"Добавьте {config['api_key_field'].upper()} в .env"
                )
                if attempt < max_attempts:
                    await self._sleep_before_retry(attempt)
                continue

            try:
                if current_provider == LLMProvider.CLAUDE:
                    response_data = await self._query_claude(
                        api_key, current_model, messages, temperature, max_tokens
                    )
                else:
                    response_data = await self._query_openai_compatible(
                        config["base_url"],
                        api_key,
                        current_model,
                        messages,
                        temperature,
                        max_tokens,
                    )
                used_provider = current_provider
                used_model = current_model
                break
            except Exception as exc:
                last_error = exc
                if not self._is_retryable_error(exc) or attempt >= max_attempts:
                    raise

                next_provider = providers_chain[attempt]
                self._logger.warning(
                    "llm_provider_fallback",
                    attempt=attempt,
                    from_provider=current_provider.value,
                    to_provider=next_provider.value,
                    error=str(exc),
                )
                await self._sleep_before_retry(attempt)

        if response_data is None or used_provider is None or used_model is None:
            if last_error:
                raise last_error
            raise RuntimeError("LLM query failed without explicit error")

        usage = self._extract_usage(response_data.get("usage"))
        self._update_token_metrics(used_provider, usage)

        if cache_key is not None:
            self._set_cached_intent(cache_key, response_data["text"])

        return LLMResponse(
            text=response_data["text"],
            provider=used_provider,
            model=used_model,
            usage=usage,
        )

    def _intent_cache_key(self, system_prompt: str | None, prompt: str) -> int | None:
        if system_prompt and "Определи intent запроса" in system_prompt:
            return hash(prompt[:100])
        return None

    def _get_cached_intent(self, cache_key: int) -> str | None:
        record = self._intent_cache.get(cache_key)
        if not record:
            return None
        cached_intent, expires_at = record
        if expires_at < time.time():
            self._intent_cache.pop(cache_key, None)
            return None
        self._intent_cache.move_to_end(cache_key)
        return cached_intent

    def _set_cached_intent(self, cache_key: int, intent: str) -> None:
        self._intent_cache[cache_key] = (intent, time.time() + self._intent_cache_ttl_seconds)
        self._intent_cache.move_to_end(cache_key)
        if len(self._intent_cache) > self._intent_cache_max_entries:
            self._intent_cache.popitem(last=False)

    def _extract_usage(self, usage: dict | None) -> dict[str, int]:
        usage = usage or {}
        tokens_input = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        tokens_output = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
        return {
            "tokens_input": tokens_input,
            "tokens_output": tokens_output,
        }

    def _update_token_metrics(self, provider: LLMProvider, usage: dict[str, int]) -> None:
        if usage["tokens_input"]:
            LLM_TOKENS_USED.labels(provider=provider.value, direction="input").inc(
                usage["tokens_input"]
            )
        if usage["tokens_output"]:
            LLM_TOKENS_USED.labels(provider=provider.value, direction="output").inc(
                usage["tokens_output"]
            )

    def _is_retryable_error(self, exc: Exception) -> bool:
        if isinstance(exc, httpx.TimeoutException):
            return True
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code in {429, 500}
        return False

    async def _sleep_before_retry(self, attempt: int) -> None:
        backoff_seconds = 2 ** (attempt - 1)
        await asyncio.sleep(backoff_seconds)

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
