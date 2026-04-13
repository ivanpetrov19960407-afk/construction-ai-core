"""Агент Critic — рецензирование черновиков."""

from typing import Any

from agents.base import AgentResult, BaseAgent
from core.llm_router import LLMRouter


class CriticAgent(BaseAgent):
    """🔎 Critic — рецензирование и проверка черновиков.

    Активируется после Author. Проверяет:
    - Полноту содержания
    - Соответствие нормативам
    - Логику изложения
    - Корректность ссылок

    Возвращает список замечаний → Author (до 5 итераций).
    """

    agent_id = "critic"
    name = "Critic"
    system_prompt = (
        "Ты — агент-рецензент строительной ИИ-платформы. "
        "Проверяешь черновики документов на полноту, соответствие нормативам, "
        "логику изложения и корректность ссылок. "
        "Формируй список замечаний с указанием критичности. "
        "Если документ готов — ответь 'APPROVED'. "
        "Если есть замечания — перечисли их для доработки Author."
    )

    def __init__(self, llm_router: LLMRouter):
        super().__init__(llm_router)

    async def execute(
        self,
        task: str,
        context: dict[str, Any] | None = None,
        previous_results: list[AgentResult] | None = None,
    ) -> AgentResult:
        """Провести рецензирование черновика."""
        prompt = f"Проведи рецензию следующего документа:\n\n{task}"
        ctx = self._build_context_prompt(previous_results)
        if ctx:
            prompt += ctx

        response = await self.llm.query(
            prompt=prompt,
            system_prompt=self.system_prompt,
        )

        # Определяем наличие замечаний
        is_approved = "APPROVED" in response.text.upper()
        issues = [] if is_approved else [response.text]

        return AgentResult(
            agent_id=self.agent_id,
            output=response.text,
            metadata={
                "approved": is_approved,
                "provider": response.provider.value,
                "model": response.model,
            },
            issues=issues,
        )
