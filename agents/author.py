"""Агент Author — генерация текстов документов."""

from __future__ import annotations

from typing import Any

from agents.base import BaseAgent
from core.llm_router import LLMRouter


class AuthorAgent(BaseAgent):
    """✍️ Author — генерирует черновик документа делового стиля."""

    system_prompt = (
        "Ты — Author агент. Сгенерируй черновик документа в деловом стиле, "
        "с чёткой структурой разделов, формальными формулировками и без разговорной лексики."
    )

    def __init__(self, llm_router: LLMRouter) -> None:
        super().__init__(agent_id="03", llm_router=llm_router)

    async def run(self, state: dict[str, Any]) -> dict[str, Any]:
        prompt = self._build_prompt(state)
        response = await self.llm_router.query(prompt=prompt, system_prompt=self.system_prompt)
        state["draft"] = response.text
        return self._update_state(state, response.text)
