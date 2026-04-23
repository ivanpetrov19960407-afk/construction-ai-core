"""Тесты WebSearchTool: graceful fallback и reuse shared client."""

import asyncio

from config.settings import settings
from core.tools.web_search import WebSearchTool


class _BrokenJsonResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self):
        raise ValueError("invalid json")


class _ClientWithBrokenJson:
    async def post(self, *args, **kwargs):
        _ = (args, kwargs)
        return _BrokenJsonResponse()


def test_web_search_returns_empty_on_invalid_json(monkeypatch):
    monkeypatch.setattr(settings, "perplexity_api_key", "test-key")
    tool = WebSearchTool(client=_ClientWithBrokenJson())

    result = asyncio.run(tool.run("test query"))

    assert result == []


def test_web_search_uses_shared_async_client():
    tool_a = WebSearchTool()
    tool_b = WebSearchTool()

    assert tool_a._client is tool_b._client

    asyncio.run(WebSearchTool.aclose_shared_client())
