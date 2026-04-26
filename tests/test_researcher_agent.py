from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

from agents.researcher import ResearcherAgent
from agents.researcher.config import ResearcherConfig
from schemas.research import Diagnostic


def _mk_agent(llm_reply: str = '{"facts": [], "gaps": []}') -> ResearcherAgent:
    llm = SimpleNamespace(query=AsyncMock(return_value=SimpleNamespace(text=llm_reply)))
    agent = ResearcherAgent(
        cast(Any, llm), config=ResearcherConfig(retry_attempts=1, llm_reask_limit=0)
    )

    class _Rag:
        async def search(
            self,
            query: str,
            n_results: int = 5,
            filter_scope: str | None = None,
            **kwargs,
        ):
            return [{"source": "СП", "page": 1, "text": "Факт", "score": 0.7}]

    agent.set_rag_engine(cast(Any, _Rag()))
    agent.set_web_search_tool(cast(Any, SimpleNamespace(run=AsyncMock(return_value=[]))))
    return agent


def test_collection_diagnostics_are_merged_and_deduplicated() -> None:
    agent = _mk_agent()
    agent._collect_sources = AsyncMock(  # type: ignore[method-assign]
        return_value=(
            [],
            [
                Diagnostic(
                    code="cache_unavailable",
                    message="x",
                    severity="warn",
                    component="source_collector",
                )
            ],
            False,
        )
    )
    result = asyncio.run(agent.run({"message": "q", "history": []}))
    payload = result["research_payload"]
    assert payload["diagnostics"].count("cache_unavailable") == 1


def test_run_handles_invalid_source_ids_via_fact_validator() -> None:
    llm_reply = (
        '{"facts":[{"text":"x","applicability":"","confidence":0.8,"source_ids":["fake"]}],'
        '"gaps":[]}'
    )
    agent = _mk_agent(llm_reply)
    result = asyncio.run(agent.run({"message": "q", "history": []}))
    payload = result["research_payload"]
    assert payload["facts"] == []
    assert "llm_hallucinated_source_id" in payload["diagnostics"]
