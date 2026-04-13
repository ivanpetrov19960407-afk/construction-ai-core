"""Агент Formatter — ГОСТ-форматирование DOCX."""

from __future__ import annotations

from typing import Any

from agents.base import BaseAgent
from core.llm_router import LLMRouter


class FormatterAgent(BaseAgent):
    """📐 Formatter — готовит структурированный dict для будущего DOCX."""

    system_prompt = (
        "Ты — Formatter агент. Сформируй структуру документа для DOCX: "
        "title, headings, sections (с подзаголовками и абзацами), tables (если есть)."
    )

    def __init__(self, llm_router: LLMRouter) -> None:
        super().__init__(agent_id="07", llm_router=llm_router)

    async def run(self, state: dict[str, Any]) -> dict[str, Any]:
        prompt = self._build_prompt(state)
        response = await self.llm_router.query(prompt=prompt, system_prompt=self.system_prompt)
        docx_payload = {
            "title": state.get("title", "Документ"),
            "headings": state.get("headings", []),
            "sections": state.get("sections", []),
            "llm_layout": response.text,
        }
        state["docx_payload"] = docx_payload
        return self._update_state(state, response.text)
