"""Агент Researcher — поиск информации по нормативам и базе знаний."""

from __future__ import annotations

from typing import Any

from agents.base import BaseAgent
from core.llm_router import LLMRouter
from core.rag_engine import RAGEngine


class ResearcherAgent(BaseAgent):
    """🔍 Researcher — поиск по нормативам и возврат структурированных фактов."""

    system_prompt = (
        "Ты — Researcher агент. Ищи факты по СП/СНиП/ГОСТ и стройнормам. "
        "Возвращай структурированно: 1) факт, 2) источник (номер документа, пункт), "
        "3) применимость. Если данных нет — явно укажи это."
    )

    def __init__(self, llm_router: LLMRouter) -> None:
        super().__init__(agent_id="01", llm_router=llm_router)
        self.rag_engine = RAGEngine()

    async def run(self, state: dict[str, Any]) -> dict[str, Any]:
        message = str(state.get("message", ""))
        chunks = await self.rag_engine.search(message)
        chunks_text = (
            "\n".join(
                f"- [{chunk['source']}, стр. {chunk['page']}] {chunk['text']}" for chunk in chunks
            )
            or "(релевантные нормативы не найдены)"
        )

        rag_prompt = f"Релевантные нормативы:\n{chunks_text}\n\nЗапрос пользователя: {message}"

        prompt = rag_prompt
        context = str(state.get("context", ""))
        if context:
            prompt = f"Контекст:\n{context}\n\n{rag_prompt}"

        response = await self.llm_router.query(prompt=prompt, system_prompt=self.system_prompt)
        state["research_facts"] = response.text
        return self._update_state(state, response.text)
