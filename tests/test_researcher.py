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
                {"source": "СП 70.13330", "page": 18, "text": "Про бетон " * 40, "score": 0.9},
                {"source": "ГОСТ 7473", "page": 5, "text": "Смесь " * 40, "score": 0.8},
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

    assert payload["facts"] == []
    assert "LLM вернул ответ не в JSON-формате" in payload["diagnostics"]


def test_researcher_drops_facts_with_invalid_source_ids():
    llm_reply = (
        '{"facts":[{"text":"Факт","applicability":"высокая","confidence":0.8,'
        '"source_ids":["missing-id"]}],"gaps":[]}'
    )
    agent = ResearcherAgent(cast(Any, _mock_llm_router(llm_reply)))

    class _Rag:
        async def search(self, query: str, n_results: int = 5, filter_scope: str | None = None):
            _ = (query, n_results, filter_scope)
            return [{"source": "СП 48", "page": 1, "text": "Факт", "score": 0.6}]

    agent.rag_engine = cast(Any, _Rag())
    agent.web_search_tool = cast(Any, SimpleNamespace(run=AsyncMock(return_value=[])))

    state = asyncio.run(agent.run({"message": "что по СП 48", "history": []}))
    payload = state["research_payload"]

    assert payload["facts"] == []
    assert any("отброшен" in msg for msg in payload["diagnostics"])


def test_researcher_does_not_cache_empty_sources():
    agent = ResearcherAgent(cast(Any, _mock_llm_router("Ответ")))

    class _Rag:
        async def search(self, query: str, n_results: int = 5, filter_scope: str | None = None):
            _ = (query, n_results, filter_scope)
            return []

    agent.rag_engine = cast(Any, _Rag())
    agent.web_search_tool = cast(Any, SimpleNamespace(run=AsyncMock(return_value=[])))
    agent.cache = cast(
        Any,
        SimpleNamespace(
            get=AsyncMock(return_value=None),
            set=AsyncMock(),
        ),
    )

    asyncio.run(agent.run({"message": "пустой поиск", "history": []}))

    assert agent.cache.set.await_count == 0


def test_researcher_cache_key_is_context_aware():
    agent = ResearcherAgent(cast(Any, _mock_llm_router("Ответ")))

    class _Rag:
        async def search(self, query: str, n_results: int = 5, filter_scope: str | None = None):
            _ = (query, n_results, filter_scope)
            return [{"source": "СП 48", "page": 1, "text": "Факт", "score": 0.6}]

    agent.rag_engine = cast(Any, _Rag())
    agent.web_search_tool = cast(Any, SimpleNamespace(run=AsyncMock(return_value=[])))
    agent.cache = cast(
        Any,
        SimpleNamespace(
            get=AsyncMock(return_value=None),
            set=AsyncMock(),
        ),
    )

    asyncio.run(agent.run({"message": "поиск", "context": "контекст 1", "history": []}))
    asyncio.run(agent.run({"message": "поиск", "context": "контекст 2", "history": []}))

    assert agent.cache.set.await_count == 2
    first_key = agent.cache.set.await_args_list[0].args[0]
    second_key = agent.cache.set.await_args_list[1].args[0]
    assert first_key != second_key
