"""Агент Formatter — ГОСТ-форматирование DOCX."""

from typing import Any

from agents.base import AgentResult, BaseAgent
from core.llm_router import LLMRouter


class FormatterAgent(BaseAgent):
    """📐 Formatter — оформление по ГОСТ Р 21.1101.

    Финальное оформление DOCX:
    - Заголовки и нумерация по ГОСТ
    - Таблицы по стандарту
    - Jinja2-шаблоны через docxtpl
    """

    agent_id = "formatter"
    name = "Formatter"
    system_prompt = (
        "Ты — агент-форматировщик строительной ИИ-платформы. "
        "Отвечаешь за финальное оформление документов по ГОСТ Р 21.1101. "
        "Преобразуй текст в структурированный формат для DOCX-шаблона: "
        "заголовки, таблицы, нумерация, подписи. "
        "Выход — JSON с данными для Jinja2-шаблона docxtpl."
    )

    def __init__(self, llm_router: LLMRouter):
        super().__init__(llm_router)

    async def execute(
        self,
        task: str,
        context: dict[str, Any] | None = None,
        previous_results: list[AgentResult] | None = None,
    ) -> AgentResult:
        """Подготовить данные для DOCX-шаблона."""
        prompt = (
            "Подготовь структурированные данные для DOCX-шаблона "
            f"(формат JSON для docxtpl):\n\n{task}"
        )
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
            metadata={
                "format": "docx_template_data",
                "provider": response.provider.value,
                "model": response.model,
            },
        )
