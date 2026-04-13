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


def test_run_pipeline_generate_tk_uses_bridge_when_available():
    """При доступности bridge оркестратор добавляет артефакты tk-generator в результат."""
    orchestrator = Orchestrator()
    orchestrator.tk_bridge.is_available = lambda: True
    orchestrator.tk_bridge.generate = AsyncMock(
        return_value={"docx_path": "/tmp/tk.docx", "pdf_path": "/tmp/tk.pdf"}
    )

    mock_calculator = AsyncMock()
    mock_calculator.run = AsyncMock(return_value={"history": [], "ks2_data": {}, "ks3_data": {}})
    orchestrator._get_agent = lambda name: mock_calculator

    orchestrator.session_memory.get = AsyncMock(return_value=[])

    orchestrator._build_graph = lambda pipeline: SimpleNamespace(
        compile=lambda: SimpleNamespace(
            ainvoke=AsyncMock(return_value={"history": [{"output": "готово"}], "confidence": 0.9})
        )
    )

    result = asyncio.run(
        orchestrator._run_pipeline(
            intent="generate_tk",
            message="сформируй тк",
            session_id="s1",
            role="pto_engineer",
            extra_state={"work_type": "Бетон", "unit": "м³", "volume": 10},
        )
    )

    assert result["reply"] == "готово"
    assert result["tk_bridge_result"]["docx_path"] == "/tmp/tk.docx"


def test_run_pipeline_generate_tk_fallback_without_bridge():
    """При недоступности bridge пайплайн продолжает работать в AI-only режиме."""
    orchestrator = Orchestrator()
    orchestrator.tk_bridge.is_available = lambda: False

    orchestrator.session_memory.get = AsyncMock(return_value=[])

    orchestrator._build_graph = lambda pipeline: SimpleNamespace(
        compile=lambda: SimpleNamespace(
            ainvoke=AsyncMock(return_value={"history": [{"output": "ai-only"}], "confidence": 0.8})
        )
    )

    result = asyncio.run(
        orchestrator._run_pipeline(
            intent="generate_tk",
            message="сформируй тк",
            session_id="s2",
            role="pto_engineer",
        )
    )

    assert result["reply"] == "ai-only"
    assert "tk_bridge_result" not in result
