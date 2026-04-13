"""Агент Calculator — детерминированные расчёты."""

from typing import Any

from agents.base import AgentResult, BaseAgent
from core.llm_router import LLMRouter


class CalculatorAgent(BaseAgent):
    """🧮 Calculator — расчёты объёмов, трудозатрат, смет.

    Детерминированные вычисления для:
    - КС-2/КС-3 (акты выполненных работ)
    - Трудозатраты и материалы для ТК
    - Сметные показатели

    В отличие от других агентов, Calculator комбинирует LLM
    (для понимания задачи) с точными математическими расчётами.
    """

    agent_id = "calculator"
    name = "Calculator"
    system_prompt = (
        "Ты — агент-калькулятор строительной ИИ-платформы. "
        "Выполняешь детерминированные расчёты объёмов работ, трудозатрат, "
        "сметных показателей для КС-2/КС-3 и технологических карт. "
        "Все расчёты должны быть точными и воспроизводимыми. "
        "Формат ответа:\n"
        "ИСХОДНЫЕ ДАННЫЕ: ...\n"
        "РАСЧЁТ: ...\n"
        "РЕЗУЛЬТАТ: ...\n"
        "Используй табличный формат для итогов."
    )

    def __init__(self, llm_router: LLMRouter):
        super().__init__(llm_router)

    async def execute(
        self,
        task: str,
        context: dict[str, Any] | None = None,
        previous_results: list[AgentResult] | None = None,
    ) -> AgentResult:
        """Выполнить расчёты."""
        prompt = f"Выполни расчёт:\n\n{task}"
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
                "calculation_type": "deterministic",
                "provider": response.provider.value,
                "model": response.model,
            },
        )
