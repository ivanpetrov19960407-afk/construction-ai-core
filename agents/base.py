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
        prompt = message
        if context:
            prompt = f"Контекст:\n{context}\n\nЗапрос:\n{message}"

        conversation_history = state.get("conversation_history", [])
        if not conversation_history:
            return prompt

        lines: list[str] = []
        for item in conversation_history:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role", "unknown"))
            content = str(item.get("content", ""))
            timestamp = str(item.get("timestamp", ""))
            lines.append(f"- [{timestamp}] {role}: {content}")

        if not lines:
            return prompt
        return f"{prompt}\n\nИстория диалога:\n" + "\n".join(lines)

    def _update_state(self, state: dict[str, Any], reply: str) -> dict[str, Any]:
        """Добавить результат агента в историю."""
        history = state.setdefault("history", [])
        if not isinstance(history, list):
            raise TypeError("state['history'] must be a list")

        history.append({"agent": self.agent_id, "output": reply})
        state["history"] = history
        return state
