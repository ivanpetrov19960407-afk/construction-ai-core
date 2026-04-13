"""Агент Analyst — анализ документации, выявление противоречий и рисков."""

from __future__ import annotations

from typing import Any

from agents.base import BaseAgent
from core.llm_router import LLMRouter


class AnalystAgent(BaseAgent):
    """📊 Analyst — выявляет противоречия и формирует отчёт о рисках."""

    system_prompt = (
        "Ты — Analyst агент. Выявляй противоречия и несоответствия в тексте. "
        "Возвращай отчёт: (а) найденные конфликты, (б) риски, (в) уровень риска "
        "(высокий/средний/низкий), (г) рекомендации."
    )

    def __init__(self, llm_router: LLMRouter) -> None:
        super().__init__(agent_id="02", llm_router=llm_router)

    async def run(self, state: dict[str, Any]) -> dict[str, Any]:
        prompt = self._build_prompt(state)
        response = await self.llm_router.query(prompt=prompt, system_prompt=self.system_prompt)
        state["risk_report"] = response.text
        return self._update_state(state, response.text)
