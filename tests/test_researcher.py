"""Тесты ResearcherAgent: RAG-first, web fallback и payload schema."""

import asyncio
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

from agents.researcher import ResearcherAgent


def _mock_llm_router(reply: str = "Факт") -> SimpleNamespace:
    return SimpleNamespace(query=AsyncMock(return_value=SimpleNamespace(text=reply)))


def test_researcher_uses_rag_first():
    agent = ResearcherAgent(cast(Any, _mock_llm_router("RAG answer")))

    class _Rag:
        async def search(self, query: str, n_results: int = 5, filter_scope: str | None = None):
            _ = (query, n_results, filter_scope)
            return [
                {"source": "СП 70.13330", "page": 18, "text": "Про бетон", "score": 0.9},
                {"source": "ГОСТ 7473", "page": 5, "text": "Смесь", "score": 0.8},
            ]

    agent.rag_engine = cast(Any, _Rag())
    agent.web_search_tool = cast(Any, SimpleNamespace(run=AsyncMock(return_value=[])))

    state = asyncio.run(agent.run({"message": "бетон", "history": []}))

    assert "research_payload" in state
    assert len(state["research_payload"]["sources"]) == 2
    assert all(source["type"] == "rag" for source in state["research_payload"]["sources"])
    assert agent.web_search_tool.run.await_count == 0


def test_researcher_falls_back_to_web_when_rag_empty():
    agent = ResearcherAgent(cast(Any, _mock_llm_router("Web answer")))

    class _Rag:
        async def search(self, query: str, n_results: int = 5, filter_scope: str | None = None):
            _ = (query, n_results, filter_scope)
            return []

    agent.rag_engine = cast(Any, _Rag())
    agent.web_search_tool = cast(
        Any,
        SimpleNamespace(
            run=AsyncMock(
                return_value=[
                    {
                        "type": "web",
                        "title": "Минстрой",
                        "url": "https://example.org",
                        "snippet": "Обновление",
                        "score": 0.7,
                    }
                ]
            )
        ),
    )

    state = asyncio.run(agent.run({"message": "новости", "history": []}))

    assert any(source["type"] == "web" for source in state["research_payload"]["sources"])
    assert agent.web_search_tool.run.await_count == 1


def test_researcher_returns_valid_json_payload():
    agent = ResearcherAgent(cast(Any, _mock_llm_router("Ответ")))

    class _Rag:
        async def search(self, query: str, n_results: int = 5, filter_scope: str | None = None):
            _ = (query, n_results, filter_scope)
            return [{"source": "СП 48", "page": 1, "text": "Факт", "score": 0.6}]

    agent.rag_engine = cast(Any, _Rag())
    agent.web_search_tool = cast(Any, SimpleNamespace(run=AsyncMock(return_value=[])))

    state = asyncio.run(agent.run({"message": "что по СП 48", "history": []}))
    payload = state["research_payload"]

    assert payload["query"] == "что по СП 48"
    assert isinstance(payload["facts"], list)
    assert isinstance(payload["sources"], list)
    assert 0 <= payload["confidence_overall"] <= 1


def test_researcher_falls_back_when_llm_returns_non_object_json():
    agent = ResearcherAgent(cast(Any, _mock_llm_router("[]")))

    class _Rag:
        async def search(self, query: str, n_results: int = 5, filter_scope: str | None = None):
            _ = (query, n_results, filter_scope)
            return [{"source": "СП 48", "page": 1, "text": "Факт", "score": 0.6}]

    agent.rag_engine = cast(Any, _Rag())
    agent.web_search_tool = cast(Any, SimpleNamespace(run=AsyncMock(return_value=[])))

    state = asyncio.run(agent.run({"message": "что по СП 48", "history": []}))
    payload = state["research_payload"]

    assert payload["facts"]
    assert payload["facts"][0]["text"] == "[]"
    assert "LLM вернул ответ не в JSON-формате" in payload["gaps"]
