"""Базовый класс агента."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from api.metrics import AGENT_RUNS
from core.llm_router import LLMRouter


class BaseAgent(ABC):
    """Базовый класс для всех агентов Construction AI."""

    agent_id: str
    system_prompt: str

    def __init__(self, agent_id: str, llm_router: LLMRouter) -> None:
        self.agent_id = agent_id
        self.llm_router = llm_router

    async def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """Запустить агента и вернуть обновлённый state."""
        try:
            result = await self._run(state)
            AGENT_RUNS.labels(agent_id=self.agent_id, status="success").inc()
            return result
        except Exception:
            AGENT_RUNS.labels(agent_id=self.agent_id, status="error").inc()
            raise

    @abstractmethod
    async def _run(self, state: dict[str, Any]) -> dict[str, Any]:
        """Внутренняя реализация выполнения конкретного агента."""

    def _build_prompt(self, state: dict[str, Any]) -> str:
        """Собрать финальный prompt из message, context и истории пайплайна."""
        message = str(state.get("message", ""))
        context = str(state.get("context", ""))
        prompt = message
        if context:
            prompt = f"Контекст:\n{context}\n\nЗапрос:\n{message}"

        conversation_history = state.get("conversation_history", [])
        conversation_lines: list[str] = []
        for item in conversation_history:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role", "unknown"))
            content = str(item.get("content", ""))
            timestamp = str(item.get("timestamp", ""))
            conversation_lines.append(f"- [{timestamp}] {role}: {content}")

        pipeline_lines = self._build_pipeline_history(state)

        sections = [prompt]
        if conversation_lines:
            sections.append("История диалога:\n" + "\n".join(conversation_lines))
        if pipeline_lines:
            sections.append("Pipeline artifacts:\n" + "\n".join(pipeline_lines))
        return "\n\n".join(sections)

    def _build_pipeline_history(self, state: dict[str, Any], *, limit: int = 3) -> list[str]:
        """Краткая выжимка последних результатов агентов и ключевых артефактов."""
        history = state.get("history", [])
        lines: list[str] = []

        if isinstance(history, list):
            for item in history[-limit:]:
                if not isinstance(item, dict):
                    continue
                agent = str(item.get("agent_name") or item.get("agent") or "unknown")
                output = str(item.get("output", "")).strip().replace("\n", " ")
                lines.append(f"- {agent}: {output[:300]}")

        artifact_keys = ["research_facts", "risk_report", "draft", "verification"]
        for key in artifact_keys:
            value = state.get(key)
            if value is None:
                continue
            text = str(value).strip().replace("\n", " ")
            lines.append(f"- {key}: {text[:240]}")
        return lines

    def _update_state(self, state: dict[str, Any], reply: str) -> dict[str, Any]:
        """Добавить результат агента в историю."""
        history = state.setdefault("history", [])
        if not isinstance(history, list):
            raise TypeError("state['history'] must be a list")

        history.append({"agent": self.agent_id, "output": reply})
        state["history"] = history
        return state
