"""Тесты health-check endpoint."""

import asyncio

from httpx import ASGITransport, AsyncClient

from api.main import app
from config.settings import settings


def test_health_has_version_and_checks():
    """Health-check должен содержать стабильные поля ответа."""

    async def _run() -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "version" in data
        assert "checks" in data
        assert "components" in data
        assert "llm" in data

    asyncio.run(_run())


def test_health_llm_degraded_when_keys_missing(monkeypatch):
    """При пустых ключах /health возвращает degraded и missing_keys."""

    monkeypatch.setattr(settings, "default_llm_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "")
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    monkeypatch.setattr(settings, "gigachat_credentials", "")
    monkeypatch.setattr(settings, "yandexgpt_api_key", "")
    monkeypatch.setattr(settings, "deepseek_api_key", "")
    monkeypatch.setattr(settings, "perplexity_api_key", "")

    async def _run() -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["llm"]["degraded"] is True
        assert data["llm"]["available"] == []
        assert set(data["checks"]["llm_router"]["missing_keys"]) == {
            "openai",
            "claude",
            "gigachat",
            "yandexgpt",
            "deepseek",
            "perplexity",
        }

    asyncio.run(_run())


def test_health_llm_ok_when_any_provider_configured(monkeypatch):
    """Если default-провайдер настроен, статус llm_router должен быть ok."""

    monkeypatch.setattr(settings, "default_llm_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "sk-test-openai")
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    monkeypatch.setattr(settings, "gigachat_credentials", "")
    monkeypatch.setattr(settings, "yandexgpt_api_key", "")
    monkeypatch.setattr(settings, "deepseek_api_key", "")
    monkeypatch.setattr(settings, "perplexity_api_key", "")

    async def _run() -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["llm"]["degraded"] is False
        assert data["checks"]["llm_router"]["status"] == "ok"
        assert "openai" in data["llm"]["available"]

    asyncio.run(_run())
