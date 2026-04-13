from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from agents.analyst import AnalystAgent
from agents.author import AuthorAgent
from agents.calculator import CalculatorAgent
from agents.critic import CriticAgent
from agents.formatter import FormatterAgent
from agents.legal_expert import LegalExpertAgent
from agents.researcher import ResearcherAgent
from agents.verifier import VerifierAgent


@pytest.fixture
def llm_router_mock() -> SimpleNamespace:
    return SimpleNamespace(query=AsyncMock(return_value=SimpleNamespace(text="ok")))


def test_researcher_smoke(llm_router_mock: SimpleNamespace) -> None:
    agent = ResearcherAgent(cast(Any, llm_router_mock))
    state = asyncio.run(agent.run({"message": "Найди СП", "context": "ПТО", "history": []}))
    assert state["history"][-1]["agent"] == "01"


def test_analyst_smoke(llm_router_mock: SimpleNamespace) -> None:
    agent = AnalystAgent(cast(Any, llm_router_mock))
    state = asyncio.run(agent.run({"message": "Проверь риски", "history": []}))
    assert state["history"][-1]["agent"] == "02"


def test_author_smoke(llm_router_mock: SimpleNamespace) -> None:
    agent = AuthorAgent(cast(Any, llm_router_mock))
    state = asyncio.run(agent.run({"message": "Сделай письмо", "history": []}))
    assert state["history"][-1]["agent"] == "03"


def test_critic_smoke(llm_router_mock: SimpleNamespace) -> None:
    llm_router_mock.query = AsyncMock(return_value=SimpleNamespace(text="APPROVED"))
    agent = CriticAgent(cast(Any, llm_router_mock))
    state = asyncio.run(
        agent.run(
            {
                "message": "Проверь",
                "history": [{"agent": "03", "output": "Черновик"}],
            }
        )
    )
    assert state["history"][-1]["output"] == "APPROVED"


def test_verifier_smoke(llm_router_mock: SimpleNamespace) -> None:
    agent = VerifierAgent(cast(Any, llm_router_mock))
    state = asyncio.run(
        agent.run(
            {
                "message": "Верифицируй",
                "history": [],
                "confidence": 0.96,
                "conflict_rate": 0.04,
                "final_text": "Финальный текст",
                "audit_log": [],
            }
        )
    )
    assert state["audit_log"][-1]["approved"] is True
    assert len(state["audit_log"][-1]["sha256"]) == 64


def test_legal_expert_smoke(llm_router_mock: SimpleNamespace) -> None:
    agent = LegalExpertAgent(cast(Any, llm_router_mock))
    state = asyncio.run(agent.run({"message": "Добавь НПА", "history": []}))
    assert state["history"][-1]["agent"] == "06"


def test_formatter_smoke(llm_router_mock: SimpleNamespace) -> None:
    agent = FormatterAgent(cast(Any, llm_router_mock))
    state = asyncio.run(
        agent.run(
            {
                "message": "Оформи",
                "history": [
                    {
                        "agent_name": "Verifier",
                        "output": """
                        Вид работ: Монолитные работы
                        Область применения: Устройство фундаментной плиты.
                        Организация и технология производства работ: Поэтапное бетонирование.
                        Требования к качеству работ: Контроль прочности.
                        Нормативные документы: СП 70.13330, ГОСТ 7473
                        """,
                    }
                ],
                "verification": {"sha256": "abc123"},
            }
        )
    )
    assert isinstance(state["docx_bytes"], bytes)
    assert state["final_output"]["template"] == "tk_template"


def test_calculator_smoke(llm_router_mock: SimpleNamespace) -> None:
    agent = CalculatorAgent(cast(Any, llm_router_mock))
    state = asyncio.run(
        agent.run(
            {
                "message": "Рассчитай",
                "history": [],
                "calculation_params": {
                    "values": {"length": 10, "width": 5},
                    "formulas": {"area": "length * width"},
                },
            }
        )
    )
    assert state["calculation_results"]["area"] == 50.0
