"""Интеграционный тест LangGraph pipeline в оркестраторе."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from core.orchestrator import Orchestrator


def test_generate_tk_pipeline_end_to_end() -> None:
    """Pipeline generate_tk должен пройти 5 агентов и собрать history."""
    orchestrator = Orchestrator()

    orchestrator.llm_router.query = AsyncMock(
        side_effect=[
            SimpleNamespace(text="research facts"),
            SimpleNamespace(text="author draft"),
            SimpleNamespace(text="APPROVED"),
            SimpleNamespace(text="verifier ok"),
            SimpleNamespace(text="formatter output"),
            SimpleNamespace(text="{}"),
        ]
    )
    # Mock session_memory.get to avoid SQLite initialisation in CI
    orchestrator.session_memory.get = AsyncMock(return_value=[])

    result = asyncio.run(
        orchestrator._run_pipeline(
            intent="generate_tk",
            message="Сделай ТК на монолитные работы",
            session_id="s-1",
            role="public",
        )
    )

    history = result["state"]["history"]
    assert len(history) == 5
    assert [item["agent_name"] for item in history] == [
        "Researcher",
        "Author",
        "Critic",
        "Verifier",
        "Formatter",
    ]
    assert result["agents_used"] == ["researcher", "author", "critic", "verifier", "formatter"]
    assert result["reply"] == "formatter output"
