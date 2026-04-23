"""Инструмент web_search с fallback на Perplexity API."""

from __future__ import annotations

from typing import Any

import httpx

from config.settings import settings
from core.tools.base import BaseTool


class WebSearchTool(BaseTool):
    """Выполняет веб-поиск через Perplexity Sonar, если настроен API ключ."""

    def __init__(self, *, timeout_seconds: float = 30.0) -> None:
        self.timeout_seconds = timeout_seconds
        self._client = httpx.AsyncClient(timeout=timeout_seconds)

    async def run(
        self,
        query: str,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Вернуть структурированные web-источники или пустой список без исключений."""
        if not settings.perplexity_api_key.strip() or not query.strip():
            return []

        max_results = int(kwargs.get("max_results", 5))
        allowed_domains = kwargs.get("allowed_domains")
        domain_text = ""
        if isinstance(allowed_domains, list) and allowed_domains:
            domain_text = f" Разрешённые домены: {', '.join(map(str, allowed_domains))}."

        try:
            response = await self._client.post(
                "https://api.perplexity.ai/chat/completions",
                headers={"Authorization": f"Bearer {settings.perplexity_api_key}"},
                json={
                    "model": "sonar",
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "Ты веб-поисковый инструмент. Верни JSON-массив объектов "
                                "с полями title,url,snippet,published_at,score."
                            ),
                        },
                        {
                            "role": "user",
                            "content": (
                                f"Запрос: {query}. Верни до {max_results} результатов.{domain_text}"
                            ),
                        },
                    ],
                    "temperature": 0,
                    "max_tokens": 800,
                },
            )
            response.raise_for_status()
        except Exception:
            return []

        payload = response.json()
        items: list[dict[str, Any]] = []
        for idx, citation in enumerate(payload.get("citations", []), start=1):
            if isinstance(citation, str):
                items.append(
                    {
                        "type": "web",
                        "title": citation,
                        "url": citation,
                        "snippet": "",
                        "published_at": None,
                        "score": max(0.0, 1.0 - (idx - 1) * 0.1),
                    }
                )

        if items:
            return items[:max_results]

        message = ""
        choices = payload.get("choices") or []
        if choices and isinstance(choices[0], dict):
            message = str((choices[0].get("message") or {}).get("content", ""))

        if message:
            return [
                {
                    "type": "web",
                    "title": "Perplexity summary",
                    "url": None,
                    "snippet": message[:500],
                    "published_at": None,
                    "score": 0.4,
                }
            ]

        return []
