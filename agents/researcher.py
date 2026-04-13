"""Агент Researcher — поиск информации по нормативам и базе знаний."""

from typing import Any

from agents.base import AgentResult, BaseAgent
from core.llm_router import LLMRouter


class ResearcherAgent(BaseAgent):
    """🔍 Researcher — поиск по нормативам, учебникам, RAG.

    Активируется при любом запросе. Ищет информацию в:
    - Нормативных документах (СП, СНиП, ГОСТ)
    - Строительных учебниках и справочниках
    - Базе знаний (RAG / ChromaDB)
    - РД и ПСД (загруженные документы)
    """

    agent_id = "researcher"
    name = "Researcher"
    system_prompt = (
        "Ты — агент-исследователь строительной ИИ-платформы. "
        "Твоя задача — найти релевантную информацию по нормативным документам "
        "(СП, СНиП, ГОСТ, МДС, ФНП), строительным учебникам и технической литературе. "
        "Всегда указывай конкретные номера документов и пункты. "
        "Если информация не найдена — честно сообщи об этом."
    )

    def __init__(self, llm_router: LLMRouter):
        super().__init__(llm_router)
        # TODO: подключить ChromaDB для RAG-поиска

    async def execute(
        self,
        task: str,
        context: dict[str, Any] | None = None,
        previous_results: list[AgentResult] | None = None,
    ) -> AgentResult:
        """Найти информацию по запросу."""
        # TODO: Фаза 2 — RAG-поиск по ChromaDB
        # Пока — прямой запрос к LLM
        prompt = f"Найди информацию по строительным нормативам:\n\n{task}"
        ctx = self._build_context_prompt(previous_results)
        if ctx:
            prompt += ctx

        response = await self.llm.query(
            prompt=prompt,
            system_prompt=self.system_prompt,
        )

        return AgentResult(
            agent_id=self.agent_id,
            output=response.text,
            metadata={"provider": response.provider.value, "model": response.model},
        )
