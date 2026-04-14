"""Тесты fallback и usage в LLMRouter."""

import asyncio
import httpx

from config.settings import settings
from core.llm_router import LLMProvider, LLMRouter


def test_query_fallback_to_next_provider_on_500(monkeypatch):
    """Если первый провайдер вернул 500, роутер должен переключиться на следующий."""
    router = LLMRouter(default_provider=LLMProvider.OPENAI)

    monkeypatch.setattr(settings, "openai_api_key", "openai-test")
    monkeypatch.setattr(settings, "perplexity_api_key", "perplexity-test")
    monkeypatch.setattr(settings, "anthropic_api_key", "anthropic-test")
    monkeypatch.setattr(settings, "deepseek_api_key", "deepseek-test")

    async def _no_sleep(_attempt: int):
        return None

    monkeypatch.setattr(router, "_sleep_before_retry", _no_sleep)

    calls: list[str] = []

    async def _mock_query_openai_compatible(
        base_url: str,
        api_key: str,
        model: str,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
    ) -> dict:
        calls.append(base_url)
        if "openai" in base_url:
            request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
            response = httpx.Response(500, request=request)
            raise httpx.HTTPStatusError("500", request=request, response=response)
        return {
            "text": "ok from fallback",
            "usage": {"prompt_tokens": 10, "completion_tokens": 20},
        }

    monkeypatch.setattr(router, "_query_openai_compatible", _mock_query_openai_compatible)

    response = asyncio.run(router.query("test prompt"))

    assert response.text == "ok from fallback"
    assert response.provider == LLMProvider.PERPLEXITY
    assert response.usage == {"tokens_input": 10, "tokens_output": 20}
    assert len(calls) == 2
    assert "openai" in calls[0]
    assert "perplexity" in calls[1]


def test_intent_detection_cache(monkeypatch):
    """Intent detection должен использовать in-memory кеш по hash(message[:100])."""
    router = LLMRouter(default_provider=LLMProvider.OPENAI)

    monkeypatch.setattr(settings, "openai_api_key", "openai-test")

    calls = 0

    async def _mock_query_openai_compatible(
        base_url: str,
        api_key: str,
        model: str,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
    ) -> dict:
        nonlocal calls
        calls += 1
        return {
            "text": "generate_tk",
            "usage": {"prompt_tokens": 5, "completion_tokens": 1},
        }

    monkeypatch.setattr(router, "_query_openai_compatible", _mock_query_openai_compatible)

    system_prompt = (
        "Определи intent запроса. Верни ровно одно слово из списка: "
        "generate_tk, generate_letter, analyze_tender, generate_ks, chat."
    )

    first = asyncio.run(router.query("сделай ТК на бетон", system_prompt=system_prompt))
    second = asyncio.run(router.query("сделай ТК на бетон", system_prompt=system_prompt))

    assert first.text == "generate_tk"
    assert second.text == "generate_tk"
    assert calls == 1
    assert second.usage == {"tokens_input": 0, "tokens_output": 0}
