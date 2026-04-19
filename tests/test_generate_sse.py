"""Тесты SSE-ошибок генерации."""

import asyncio

from api.routes import generate
from core.errors import LLMProviderNotConfiguredError


def test_emit_error_returns_llm_not_configured_payload():
    """_emit_error формирует корректный SSE payload для llm_not_configured."""
    queue: asyncio.Queue[str] = asyncio.Queue()

    asyncio.run(
        generate._emit_error(
            queue,
            code="llm_not_configured",
            message="LLM-провайдер не настроен. Добавьте ключ в Настройках",
            details={"provider": "openai", "missing_setting": "OPENAI_API_KEY"},
        )
    )

    payload = asyncio.run(queue.get())
    assert "event: error" in payload
    assert '"code": "llm_not_configured"' in payload
    assert "OPENAI_API_KEY" in payload


def test_exception_to_http_maps_llm_provider_not_configured():
    """LLMProviderNotConfiguredError -> HTTP detail.code=llm_not_configured."""
    exc = LLMProviderNotConfiguredError(provider="openai", missing_setting="OPENAI_API_KEY")

    mapped = generate._exception_to_http(exc)

    assert mapped.status_code == 503
    assert mapped.detail["code"] == "llm_not_configured"
    assert mapped.detail["message"] == "LLM-провайдер не настроен. Добавьте ключ в Настройках"
    assert mapped.detail["details"]["provider"] == "openai"
