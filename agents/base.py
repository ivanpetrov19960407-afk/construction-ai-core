"""Базовый класс агента."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from core.llm_router import LLMRouter


class BaseAgent(ABC):
    """Базовый класс для всех агентов Construction AI."""

    agent_id: str
    system_prompt: str

    def __init__(self, agent_id: str, llm_router: LLMRouter) -> None:
        self.agent_id = agent_id
        self.llm_router = llm_router

    @abstractmethod
    async def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """Запустить агента и вернуть обновлённый state."""

    def _build_prompt(self, state: dict[str, Any]) -> str:
        """Собрать финальный prompt из message и context."""
        message = str(state.get("message", ""))
        context = str(state.get("context", ""))
        if context:
            return f"Контекст:\n{context}\n\nЗапрос:\n{message}"
        return message

    def _update_state(self, state: dict[str, Any], reply: str) -> dict[str, Any]:
        """Добавить результат агента в историю."""
        history = state.setdefault("history", [])
        if not isinstance(history, list):
            raise TypeError("state['history'] must be a list")

        history.append({"agent": self.agent_id, "output": reply})
        state["history"] = history
        return state
