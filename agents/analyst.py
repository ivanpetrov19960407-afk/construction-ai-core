"""Агент Analyst — анализ документации, выявление противоречий и рисков."""

from typing import Any

from agents.base import AgentResult, BaseAgent
from core.llm_router import LLMRouter


class AnalystAgent(BaseAgent):
    """📊 Analyst — конфликт-анализ и оценка рисков.

    Активируется при анализе документов и тендеров.
    Выявляет противоречия, несоответствия нормативам, риски.
    """

    agent_id = "analyst"
    name = "Analyst"
    system_prompt = (
        "Ты — агент-аналитик строительной ИИ-платформы. "
        "Твоя задача — выявлять противоречия, конфликты и риски в документации. "
        "Анализируй на соответствие нормативам (СП, СНиП, ГОСТ). "
        "Формируй структурированный отчёт: риски, несоответствия, рекомендации. "
        "Используй шкалу критичности: ВЫСОКИЙ / СРЕДНИЙ / НИЗКИЙ."
    )

    def __init__(self, llm_router: LLMRouter):
        super().__init__(llm_router)

    async def execute(
        self,
        task: str,
        context: dict[str, Any] | None = None,
        previous_results: list[AgentResult] | None = None,
    ) -> AgentResult:
        """Провести анализ документации."""
        prompt = f"Проанализируй документацию и выяви риски/противоречия:\n\n{task}"
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
