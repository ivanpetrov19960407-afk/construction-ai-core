"""Тесты intent-детекции оркестратора."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from core.orchestrator import Orchestrator


def test_detect_intent_generate_tk():
    """Фраза про ТК должна маршрутизироваться в generate_tk."""
    orchestrator = Orchestrator()
    orchestrator.llm_router.query = AsyncMock(return_value=SimpleNamespace(text="generate_tk"))

    intent = asyncio.run(orchestrator._detect_intent("сделай ТК на бетонирование"))

    assert intent == "generate_tk"


def test_detect_intent_generate_letter():
    """Фраза про письмо подрядчику должна маршрутизироваться в generate_letter."""
    orchestrator = Orchestrator()
    orchestrator.llm_router.query = AsyncMock(return_value=SimpleNamespace(text="generate_letter"))

    intent = asyncio.run(orchestrator._detect_intent("напиши письмо подрядчику"))

    assert intent == "generate_letter"
