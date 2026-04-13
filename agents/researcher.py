"""Агент Researcher — поиск информации по нормативам и базе знаний."""

from __future__ import annotations

from typing import Any

from agents.base import BaseAgent
from core.llm_router import LLMRouter


class ResearcherAgent(BaseAgent):
    """🔍 Researcher — поиск по нормативам и возврат структурированных фактов."""

    system_prompt = (
        "Ты — Researcher агент. Ищи факты по СП/СНиП/ГОСТ и стройнормам. "
        "Возвращай структурированно: 1) факт, 2) источник (номер документа, пункт), "
        "3) применимость. Если данных нет — явно укажи это."
    )

    def __init__(self, llm_router: LLMRouter) -> None:
        super().__init__(agent_id="01", llm_router=llm_router)

    async def run(self, state: dict[str, Any]) -> dict[str, Any]:
        prompt = self._build_prompt(state)
        response = await self.llm_router.query(prompt=prompt, system_prompt=self.system_prompt)
        state["research_facts"] = response.text
        return self._update_state(state, response.text)
