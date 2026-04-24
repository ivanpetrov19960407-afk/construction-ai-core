"""Deprecation-warning tests for legacy scope/role keys in ResearcherAgent."""

from __future__ import annotations

import asyncio
import warnings
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

from agents.researcher import ResearcherAgent


class _Rag:
    async def search(self, query: str, n_results: int = 5, filter_scope: str | None = None):
        _ = (query, n_results, filter_scope)
        return [
            {"source": "СП 48", "page": 1, "text": "Обычный текст про бетон " * 20, "score": 0.8},
            {"source": "ГОСТ 7473", "page": 2, "text": "Смесь бетонная " * 20, "score": 0.75},
        ]


def _mk_agent() -> ResearcherAgent:
    llm = SimpleNamespace(
        query=AsyncMock(return_value=SimpleNamespace(text='{"facts": [], "gaps": []}'))
    )
    agent = ResearcherAgent(cast(Any, llm))
    agent.rag_engine = cast(Any, _Rag())
    agent.web_search_tool = cast(Any, SimpleNamespace(run=AsyncMock(return_value=[])))
    return agent


def test_legacy_scope_triggers_deprecation_warning() -> None:
    agent = _mk_agent()
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        asyncio.run(agent.run({"message": "бетон", "history": [], "scope": "pto_engineer"}))
    assert any(
        issubclass(w.category, DeprecationWarning) and "access_scope" in str(w.message)
        for w in recorded
    ), "Deprecation warning must be emitted for legacy 'scope' key"


def test_legacy_role_triggers_deprecation_warning() -> None:
    agent = _mk_agent()
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        asyncio.run(agent.run({"message": "бетон", "history": [], "role": "foreman"}))
    assert any(issubclass(w.category, DeprecationWarning) for w in recorded), (
        "Deprecation warning must be emitted for legacy 'role' key"
    )


def test_explicit_access_scope_emits_no_warning() -> None:
    agent = _mk_agent()
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        asyncio.run(agent.run({"message": "бетон", "history": [], "access_scope": "pto_engineer"}))
    assert not any(issubclass(w.category, DeprecationWarning) for w in recorded), (
        "No deprecation warning expected when 'access_scope' is explicit"
    )
