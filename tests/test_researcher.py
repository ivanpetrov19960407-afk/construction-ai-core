from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

from agents.researcher import ResearcherAgent
from agents.researcher.config import ResearcherConfig


def _mk_agent(llm_reply: str = '{"facts": [], "gaps": []}') -> ResearcherAgent:
    llm = SimpleNamespace(query=AsyncMock(return_value=SimpleNamespace(text=llm_reply)))
    agent = ResearcherAgent(cast(Any, llm), config=ResearcherConfig(retry_attempts=1, llm_reask_limit=0))

    class _Rag:
        async def search(self, query: str, n_results: int = 5, filter_scope: str | None = None, **kwargs):
            return [{"source": "СП", "page": 1, "text": "Факт", "score": 0.7}]

    agent.set_rag_engine(cast(Any, _Rag()))
    agent.set_web_search_tool(cast(Any, SimpleNamespace(run=AsyncMock(return_value=[]))))
    return agent


def test_researcher_falls_back_when_llm_returns_non_object_json() -> None:
    agent = _mk_agent("[]")
    state = asyncio.run(agent.run({"message": "что по СП", "history": []}))
    payload = state["research_payload"]
    assert payload["facts"] == []
    assert "llm_schema_validation_failure" in payload["diagnostics"] or "llm_malformed_json" in payload["diagnostics"]


def test_researcher_drops_facts_with_invalid_source_ids() -> None:
    agent = _mk_agent('{"facts":[{"text":"x","applicability":"","confidence":0.8,"source_ids":["bad"]}],"gaps":[]}')
    state = asyncio.run(agent.run({"message": "что по СП", "history": []}))
    payload = state["research_payload"]
    assert payload["facts"] == []
    assert "llm_hallucinated_source_id" in payload["diagnostics"]
