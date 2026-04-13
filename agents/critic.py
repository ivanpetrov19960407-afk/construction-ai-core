"""Агент Critic — рецензирование черновиков."""

from __future__ import annotations

from typing import Any

from agents.base import BaseAgent
from core.llm_router import LLMRouter


class CriticAgent(BaseAgent):
    """🔎 Critic — проверяет черновик и возвращает замечания или APPROVED."""

    system_prompt = (
        "Ты — Critic агент. Проверь черновик: полнота, логика, стиль, ссылки на нормы. "
        "Если всё корректно, верни только 'APPROVED'. Иначе верни список замечаний по пунктам."
    )

    def __init__(self, llm_router: LLMRouter) -> None:
        super().__init__(agent_id="04", llm_router=llm_router)

    async def _run(self, state: dict[str, Any]) -> dict[str, Any]:
        history = state.get("history", [])
        if not isinstance(history, list):
            raise TypeError("state['history'] must be a list")

        author_output = ""
        for item in reversed(history):
            if isinstance(item, dict) and item.get("agent") == "03":
                author_output = str(item.get("output", ""))
                break

        if not author_output:
            raise ValueError("Author output not found in state['history']")

        prompt = f"Черновик автора для проверки:\n\n{author_output}"
        response = await self.llm_router.query(prompt=prompt, system_prompt=self.system_prompt)
        review = response.text.strip()
        state["critic_verdict"] = review
        return self._update_state(state, "APPROVED" if review.upper() == "APPROVED" else review)
