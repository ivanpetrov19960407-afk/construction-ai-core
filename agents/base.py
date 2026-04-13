"""Базовый класс агента."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from core.llm_router import LLMRouter


@dataclass
class AgentResult:
    """Результат работы агента."""

    agent_id: str
    output: str
    metadata: dict[str, Any] = field(default_factory=dict)
    confidence: float | None = None
    issues: list[str] = field(default_factory=list)


class BaseAgent(ABC):
    """Базовый класс для всех агентов Construction AI.

    Каждый агент:
    - Имеет уникальный ID и системный промпт
    - Получает контекст задачи и предыдущие результаты
    - Возвращает AgentResult
    """

    agent_id: str
    name: str
    system_prompt: str

    def __init__(self, llm_router: LLMRouter):
        self.llm = llm_router

    @abstractmethod
    async def execute(
        self,
        task: str,
        context: dict[str, Any] | None = None,
        previous_results: list[AgentResult] | None = None,
    ) -> AgentResult:
        """Выполнить задачу агента.

        Args:
            task: Текст задачи / запроса.
            context: Дополнительный контекст (файлы, параметры).
            previous_results: Результаты предыдущих агентов в pipeline.

        Returns:
            AgentResult с выходными данными.
        """
        ...

    def _build_context_prompt(self, previous_results: list[AgentResult] | None) -> str:
        """Сформировать контекст из результатов предыдущих агентов."""
        if not previous_results:
            return ""
        parts = []
        for r in previous_results:
            parts.append(f"[{r.agent_id}]: {r.output[:2000]}")
        return "\n\n--- Результаты предыдущих агентов ---\n" + "\n".join(parts)
