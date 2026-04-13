"""Агент Legal Expert — проверка ссылок на НПА."""

from __future__ import annotations

from typing import Any

from agents.base import BaseAgent
from core.llm_router import LLMRouter


class LegalExpertAgent(BaseAgent):
    """⚖️ Legal Expert — добавляет ссылки на ФЗ/ГК РФ/ТК РФ."""

    system_prompt = (
        "Ты — Legal Expert агент. Проверь юридические формулировки и добавь релевантные "
        "ссылки на ФЗ, ГК РФ, ТК РФ (статья/часть/пункт). Верни правки списком."
    )

    def __init__(self, llm_router: LLMRouter) -> None:
        super().__init__(agent_id="06", llm_router=llm_router)

    async def _run(self, state: dict[str, Any]) -> dict[str, Any]:
        prompt = self._build_prompt(state)
        response = await self.llm_router.query(prompt=prompt, system_prompt=self.system_prompt)
        state["legal_review"] = response.text
        return self._update_state(state, response.text)
