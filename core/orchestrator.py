"""Оркестратор — координирует работу 8 агентов.

Supervisor-паттерн на LangGraph. Управляет pipeline'ами:
- generate_tk: Researcher → Author → Critic → Verifier → Formatter
- generate_letter: Researcher → Author → Legal Expert → Critic → Verifier → Formatter
- analyze_tender: Researcher → Analyst → Legal Expert → Verifier
- generate_ks: Researcher → Calculator → Author → Critic → Verifier → Formatter
"""

import json
import uuid
from pathlib import Path
from typing import Any

from core.llm_router import LLMRouter


class Orchestrator:
    """Главный оркестратор Construction AI.

    Загружает конфигурацию агентов из orchestrator.json и координирует
    их работу в соответствии с заданным pipeline.
    """

    def __init__(self, config_path: str | None = None):
        self.config_path = config_path or str(
            Path(__file__).parent.parent / "config" / "orchestrator.json"
        )
        self.config = self._load_config()
        self.llm_router = LLMRouter()
        self.agents: dict[str, dict] = {
            agent["id"]: agent for agent in self.config["agents"]
        }

    def _load_config(self) -> dict:
        """Загрузить конфигурацию оркестратора."""
        with open(self.config_path) as f:
            return json.load(f)

    async def process(
        self,
        message: str,
        session_id: str | None = None,
        role: str = "pto_engineer",
    ) -> dict[str, Any]:
        """Обработать запрос пользователя.

        1. Определить intent (тип задачи)
        2. Выбрать pipeline
        3. Последовательно вызвать агентов
        4. Вернуть результат

        Args:
            message: Сообщение пользователя.
            session_id: ID сессии (для контекста).
            role: Роль пользователя.

        Returns:
            Словарь с ответом и метаданными.
        """
        session_id = session_id or str(uuid.uuid4())

        # TODO: Фаза 1 — базовый чат через LLM Router
        # Пока без полноценного pipeline, просто прямой запрос к LLM
        system_prompt = self._build_system_prompt(role)

        try:
            response = await self.llm_router.query(
                prompt=message,
                system_prompt=system_prompt,
            )
            return {
                "reply": response.text,
                "session_id": session_id,
                "agents_used": ["researcher"],  # базовый режим
                "confidence": None,
            }
        except Exception as e:
            return {
                "reply": f"Ошибка обработки: {e}",
                "session_id": session_id,
                "agents_used": [],
                "confidence": None,
            }

    def _build_system_prompt(self, role: str) -> str:
        """Построить системный промпт на основе роли пользователя."""
        role_prompts = {
            "pto_engineer": (
                "Ты — ИИ-помощник инженера ПТО в строительной компании. "
                "Помогаешь с технологическими картами, ППР, нормативами (СП, СНиП, ГОСТ). "
                "Отвечай точно, со ссылками на нормативные документы."
            ),
            "foreman": (
                "Ты — ИИ-помощник прораба / зам. генерального директора. "
                "Помогаешь с деловой перепиской, запросами подрядчикам, "
                "контролем выполнения работ. Стиль — деловой, со ссылками на НПА."
            ),
            "tender_specialist": (
                "Ты — ИИ-помощник специалиста по тендерам. "
                "Анализируешь тендерную документацию, выявляешь риски, "
                "проверяешь соответствие нормативам."
            ),
            "admin": (
                "Ты — ИИ-помощник Construction AI. Можешь выполнять любые задачи: "
                "генерация документов, анализ, консультации по нормативам."
            ),
        }
        return role_prompts.get(role, role_prompts["admin"])

    def get_workflow(self, workflow_name: str) -> list[str] | None:
        """Получить pipeline для указанного workflow."""
        workflows = self.config.get("workflows", {})
        wf = workflows.get(workflow_name)
        return wf["pipeline"] if wf else None

    def list_agents(self) -> list[dict]:
        """Список всех агентов с их конфигурацией."""
        return self.config["agents"]
