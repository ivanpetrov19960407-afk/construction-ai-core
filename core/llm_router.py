"""LLM Router — маршрутизация запросов к нужному LLM-провайдеру.

Позволяет менять провайдера без изменения бизнес-логики.
Поддерживаемые провайдеры: Perplexity, OpenAI, Claude, Deepseek.
"""

import asyncio
import hashlib
from dataclasses import dataclass
from enum import Enum

import httpx
import structlog

from api.metrics import LLM_TOKENS_USED
from config.settings import settings
from core.cache import RedisCache
from core.errors import LLMProviderNotConfiguredError


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
        self._cache = RedisCache(settings.redis_url)
        self._intent_cache_ttl_seconds = 3600
        self.available_providers: set[LLMProvider] = self._detect_available_providers()
        self._logger.info(
            "llm_router_initialized",
            default_provider=self.default_provider.value,
            available_providers=sorted(provider.value for provider in self.available_providers),
        )

    def _detect_available_providers(self) -> set[LLMProvider]:
        return {provider for provider in LLMProvider if self._provider_api_key(provider).strip()}

    def _provider_api_key_field(self, provider: LLMProvider) -> str:
        return str(PROVIDER_CONFIG[provider]["api_key_field"])

    def _provider_api_key(self, provider: LLMProvider) -> str:
        return str(getattr(settings, self._provider_api_key_field(provider), ""))

    def is_available(self, provider: LLMProvider | str) -> bool:
        resolved = provider if isinstance(provider, LLMProvider) else LLMProvider(provider)
        return bool(self._provider_api_key(resolved).strip())

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
        requested_provider = provider or self.default_provider
        self.available_providers = self._detect_available_providers()
        if not self.is_available(requested_provider):
            raise LLMProviderNotConfiguredError(
                requested_provider.value,
                self._provider_api_key_field(requested_provider),
            )

        providers_chain = [
            requested_provider,
            *[
                candidate
                for candidate in LLMProvider
                if candidate != requested_provider and candidate in self.available_providers
            ],
        ]

        # Формируем messages
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        cache_key = self._intent_cache_key(system_prompt, prompt)
        if cache_key is not None:
            cached_intent = await self._cache.get(cache_key)
            if cached_intent is not None:
                return LLMResponse(
                    text=cached_intent,
                    provider=requested_provider,
                    model=model or PROVIDER_CONFIG[requested_provider]["default_model"],
                    usage={"tokens_input": 0, "tokens_output": 0},
                )

        response_data = None
        used_provider = None
        used_model = None
        max_attempts = min(3, len(providers_chain))
        last_error: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            current_provider = providers_chain[attempt - 1]
            config = PROVIDER_CONFIG[current_provider]
            current_model = model or config["default_model"]
            api_key = self._provider_api_key(current_provider)

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
            await self._cache.set(
                cache_key,
                response_data["text"],
                ttl=self._intent_cache_ttl_seconds,
            )

        return LLMResponse(
            text=response_data["text"],
            provider=used_provider,
            model=used_model,
            usage=usage,
        )

    def _intent_cache_key(self, system_prompt: str | None, prompt: str) -> str | None:
        if system_prompt and "Определи intent запроса" in system_prompt:
            digest = hashlib.sha256(prompt[:100].encode("utf-8")).hexdigest()
            return f"llm:{digest}"
        return None

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
        """Запрос к Claude API (Anthropic)."""
        system = None
        anthropic_messages = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")
            if role == "system":
                system = content
            elif role in {"user", "assistant"}:
                anthropic_messages.append({"role": role, "content": content})

        payload = {
            "model": model,
            "messages": anthropic_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if system:
            payload["system"] = system

        response = await self._client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        content_blocks = data.get("content", [])
        text_parts = [
            block.get("text", "") for block in content_blocks if block.get("type") == "text"
        ]
        return {
            "text": "\n".join(part for part in text_parts if part),
            "usage": data.get("usage"),
        }
