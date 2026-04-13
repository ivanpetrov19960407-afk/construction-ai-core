"""Агент Author — генерация текстов документов."""

from typing import Any

from agents.base import AgentResult, BaseAgent
from core.llm_router import LLMRouter


class AuthorAgent(BaseAgent):
    """✍️ Author — генерация ТК, ППР, писем, отчётов.

    Активируется при генерации документов.
    Черновик передаётся агенту Critic для рецензирования.
    """

    agent_id = "author"
    name = "Author"
    system_prompt = (
        "Ты — агент-автор строительной ИИ-платформы. "
        "Генерируешь тексты технологических карт (ТК), проектов производства работ (ППР), "
        "деловых писем и отчётов. Деловой стиль, формальные требования. "
        "Структурируй текст по разделам согласно СП 48.13330. "
        "Используй данные от агента Researcher."
    )

    def __init__(self, llm_router: LLMRouter):
        super().__init__(llm_router)

    async def execute(
        self,
        task: str,
        context: dict[str, Any] | None = None,
        previous_results: list[AgentResult] | None = None,
    ) -> AgentResult:
        """Сгенерировать текст документа."""
        prompt = f"Сгенерируй текст документа:\n\n{task}"
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
