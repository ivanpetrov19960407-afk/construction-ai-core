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
from typing import Any, TypedDict, cast

from langgraph.graph import END, START, StateGraph

from agents.analyst import AnalystAgent
from agents.author import AuthorAgent
from agents.calculator import CalculatorAgent
from agents.critic import CriticAgent
from agents.formatter import FormatterAgent
from agents.legal_expert import LegalExpertAgent
from agents.researcher import ResearcherAgent
from agents.verifier import VerifierAgent
from api.metrics import PIPELINE_DURATION
from core.llm_router import LLMRouter
from core.session_memory import SessionMemory


class PipelineState(TypedDict):
    """Состояние выполнения workflow в LangGraph."""

    message: str
    session_id: str
    role: str
    history: list[dict]
    audit_log: list[dict]
    critic_iterations: int
    final_output: str | None
    conversation_history: list[dict[str, str]]


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
        self.session_memory = SessionMemory()
        self.agents: dict[str, dict] = {agent["id"]: agent for agent in self.config["agents"]}

    def _load_config(self) -> dict:
        """Загрузить конфигурацию оркестратора."""
        with open(self.config_path) as f:
            return json.load(f)

    async def _detect_intent(self, message: str) -> str:
        """Определить intent пользовательского запроса через LLMRouter."""
        system_prompt = (
            "Определи intent запроса. "
            "Верни ровно одно слово из списка: "
            "generate_tk, generate_letter, analyze_tender, generate_ks, chat."
        )
        response = await self.llm_router.query(
            prompt=message,
            system_prompt=system_prompt,
        )

        intent = response.text.strip().lower()
        if intent == "chat":
            return intent
        return intent if self.get_workflow(intent) else "chat"

    def _get_agent(self, name: str):
        """Вернуть инстанс агента по его id из config."""
        factory = {
            "researcher": ResearcherAgent,
            "analyst": AnalystAgent,
            "author": AuthorAgent,
            "critic": CriticAgent,
            "verifier": VerifierAgent,
            "legal_expert": LegalExpertAgent,
            "formatter": FormatterAgent,
            "calculator": CalculatorAgent,
        }
        agent_class = factory.get(name)
        if not agent_class:
            raise ValueError(f"Unknown agent: {name}")
        return cast(Any, agent_class)(self.llm_router)

    def _agent_display_name(self, name: str) -> str:
        """Человекочитаемое имя агента для history."""
        labels = {
            "researcher": "Researcher",
            "analyst": "Analyst",
            "author": "Author",
            "critic": "Critic",
            "verifier": "Verifier",
            "legal_expert": "LegalExpert",
            "formatter": "Formatter",
            "calculator": "Calculator",
        }
        return labels.get(name, name)

    def _build_graph(self, pipeline: list[str]) -> StateGraph:
        """Построить LangGraph StateGraph для указанного pipeline."""
        graph = StateGraph(PipelineState)

        for node_name in pipeline:
            agent = self._get_agent(node_name)

            async def _runner(state: PipelineState, _agent=agent, _node_name=node_name):
                updated_state = await _agent.run(state)
                history = updated_state.get("history", [])
                if history and isinstance(history[-1], dict):
                    history[-1]["agent_name"] = self._agent_display_name(_node_name)
                    updated_state["final_output"] = str(history[-1].get("output", ""))
                return updated_state

            graph.add_node(node_name, _runner)

        if not pipeline:
            return graph

        graph.add_edge(START, pipeline[0])

        for idx, node_name in enumerate(pipeline):
            is_last = idx == len(pipeline) - 1
            if is_last:
                graph.add_edge(node_name, END)
                continue

            next_node = pipeline[idx + 1]
            if node_name != "critic":
                graph.add_edge(node_name, next_node)
                continue

            author_node = "author" if "author" in pipeline else next_node

            def _critic_decision(state: PipelineState) -> str:
                history = state.get("history", [])
                last_output = ""
                if history and isinstance(history[-1], dict):
                    last_output = str(history[-1].get("output", ""))

                iterations = int(state.get("critic_iterations", 0))
                if "APPROVED" in last_output.upper():
                    return "approved"
                if iterations >= 5:
                    return "approved"
                state["critic_iterations"] = iterations + 1
                return "revise"

            graph.add_conditional_edges(
                "critic",
                _critic_decision,
                {"approved": next_node, "revise": author_node},
            )

        return graph

    async def _run_pipeline(
        self,
        intent: str,
        message: str,
        session_id: str,
        role: str,
        include_legal_expert: bool = True,
        extra_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Запустить workflow по intent через LangGraph."""
        pipeline = self.get_workflow(intent)
        if intent == "generate_letter" and not include_legal_expert and isinstance(pipeline, list):
            pipeline = [agent for agent in pipeline if agent != "legal_expert"]
        if not pipeline:
            return {
                "reply": None,
                "session_id": session_id,
                "agents_used": [],
                "confidence": None,
            }

        graph = self._build_graph(pipeline).compile()
        initial_state: PipelineState = {
            "message": message,
            "session_id": session_id,
            "role": role,
            "conversation_history": await self.session_memory.get(session_id, last_n=10),
            "history": [],
            "audit_log": [],
            "critic_iterations": 0,
            "final_output": None,
        }
        if extra_state:
            initial_state = cast(PipelineState, {**initial_state, **extra_state})

        with PIPELINE_DURATION.labels(intent=intent).time():
            final_state = await cast(Any, graph).ainvoke(initial_state)
        return {
            "reply": final_state.get("final_output"),
            "session_id": session_id,
            "agents_used": pipeline,
            "confidence": final_state.get("confidence"),
            "state": final_state,
        }

    async def process(
        self,
        message: str,
        session_id: str | None = None,
        role: str = "pto_engineer",
        intent: str | None = None,
        include_legal_expert: bool = True,
        extra_state: dict[str, Any] | None = None,
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
            intent: Принудительный intent (если задан, без LLM-детекции).

        Returns:
            Словарь с ответом и метаданными.
        """
        session_id = session_id or str(uuid.uuid4())
        await self.session_memory.add(session_id, role="user", content=message)

        intent = intent or await self._detect_intent(message)

        if intent != "chat":
            result = await self._run_pipeline(
                intent,
                message,
                session_id,
                role,
                include_legal_expert=include_legal_expert,
                extra_state=extra_state,
            )
            if result.get("reply"):
                await self.session_memory.add(
                    session_id, role="assistant", content=str(result["reply"])
                )
            return result

        # TODO: Фаза 1 — базовый чат через LLM Router
        # Пока без полноценного pipeline, просто прямой запрос к LLM
        system_prompt = self._build_system_prompt(role)

        try:
            response = await self.llm_router.query(
                prompt=message,
                system_prompt=system_prompt,
            )
            await self.session_memory.add(session_id, role="assistant", content=response.text)
            return {
                "reply": response.text,
                "session_id": session_id,
                "agents_used": ["researcher"],  # базовый режим
                "confidence": None,
            }
        except Exception as e:
            await self.session_memory.add(
                session_id,
                role="assistant",
                content=f"Ошибка обработки: {e}",
            )
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
