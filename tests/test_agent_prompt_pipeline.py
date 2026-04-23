"""Проверка попадания результатов предыдущих агентов в prompt следующего."""

from types import SimpleNamespace
from typing import Any

from agents.base import BaseAgent


class _DummyAgent(BaseAgent):
    async def _run(self, state: dict[str, Any]) -> dict[str, Any]:
        return state


def test_build_prompt_includes_pipeline_history_and_artifacts() -> None:
    agent = _DummyAgent(agent_id="99", llm_router=SimpleNamespace())
    state = {
        "message": "Сделай вывод",
        "context": "Контекст",
        "conversation_history": [{"role": "user", "content": "Ранее", "timestamp": "t1"}],
        "history": [
            {"agent_name": "Researcher", "output": "Нашел ГОСТ"},
            {"agent_name": "Analyst", "output": "Риск высокий"},
        ],
        "research_facts": "ГОСТ 123",
    }

    prompt = agent._build_prompt(state)

    assert "История диалога" in prompt
    assert "Pipeline artifacts" in prompt
    assert "Researcher" in prompt
    assert "research_facts" in prompt
