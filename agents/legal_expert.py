"""Агент Legal Expert — проверка ссылок на НПА."""

from typing import Any

from agents.base import AgentResult, BaseAgent
from core.llm_router import LLMRouter


class LegalExpertAgent(BaseAgent):
    """⚖️ Legal Expert — юридическая проверка.

    Проверяет ссылки на НПА: ФЗ, ГК РФ, ТК РФ, договорные условия.
    Формулировки претензий. Активируется при генерации писем и анализе тендеров.
    """

    agent_id = "legal_expert"
    name = "Legal Expert"
    system_prompt = (
        "Ты — юридический агент строительной ИИ-платформы. "
        "Проверяешь и добавляешь ссылки на нормативно-правовые акты: "
        "ФЗ, ГК РФ, ТК РФ, Градостроительный кодекс, договорные условия. "
        "Проверяешь корректность формулировок претензий и уведомлений. "
        "Указывай конкретные статьи и пункты."
    )

    def __init__(self, llm_router: LLMRouter):
        super().__init__(llm_router)

    async def execute(
        self,
        task: str,
        context: dict[str, Any] | None = None,
        previous_results: list[AgentResult] | None = None,
    ) -> AgentResult:
        """Провести юридическую проверку."""
        prompt = f"Проведи юридическую проверку документа:\n\n{task}"
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
