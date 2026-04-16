"""Тесты генерации КС-2/КС-3."""

import asyncio
import importlib.util
from unittest.mock import AsyncMock

from agents.calculator import CalculatorAgent
from config.settings import settings
from core.llm_router import LLMRouter


def test_calculator_totals_match_subtotals_for_3_items():
    """Calculator считает итоги как сумму subtotals для 3 позиций."""

    class DummyRouter(LLMRouter):
        pass

    agent = CalculatorAgent(DummyRouter())
    state = {
        "period_from": "2026-01-01",
        "period_to": "2026-01-31",
        "calculation_params": {
            "work_items": [
                {
                    "name": "Бетонирование",
                    "unit": "м³",
                    "volume": 10,
                    "norm_hours": 2,
                    "price_per_unit": 5000,
                },
                {
                    "name": "Армирование",
                    "unit": "т",
                    "volume": 2,
                    "norm_hours": 8,
                    "price_per_unit": 30000,
                },
                {
                    "name": "Опалубка",
                    "unit": "м²",
                    "volume": 25,
                    "norm_hours": 0.6,
                    "price_per_unit": 700,
                },
            ]
        },
        "history": [],
    }

    result_state = asyncio.run(agent.run(state))
    ks2 = result_state["ks2_data"]
    subtotals_sum = sum(item["subtotal_cost"] for item in ks2["work_items"])

    assert len(ks2["work_items"]) == 3
    assert ks2["total_cost"] == subtotals_sum


def test_generate_ks_endpoint_forces_intent_generate_ks():
    """POST /api/generate/ks принудительно вызывает intent=generate_ks."""
    if importlib.util.find_spec("multipart") is None:
        return

    from fastapi.testclient import TestClient

    from api.main import app
    from api.routes import generate

    old_keys = settings.api_keys
    settings.api_keys = ["valid-key"]
    mocked_process = AsyncMock(
        return_value={
            "session_id": "session-ks-1",
            "state": {
                "ks2_data": {
                    "work_items": [
                        {"subtotal_cost": 10.0},
                        {"subtotal_cost": 20.0},
                        {"subtotal_cost": 30.0},
                    ],
                    "total_cost": 60.0,
                    "total_hours": 12.0,
                },
                "ks3_data": {"workers_needed": 1},
                "verification": {"sha256": "abc"},
            },
        }
    )
    generate.orchestrator.process = mocked_process
    captured_upsert: dict[str, object] = {}

    def _mock_upsert_generated_doc(doc_id: str, doc_type: str, payload: dict) -> None:
        captured_upsert["doc_id"] = doc_id
        captured_upsert["doc_type"] = doc_type
        captured_upsert["payload"] = payload

    original_upsert = generate._upsert_generated_doc
    generate._upsert_generated_doc = _mock_upsert_generated_doc

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/generate/ks",
                json={
                    "object_name": "ЖК Север",
                    "contract_number": "Д-77",
                    "period_from": "2026-01-01",
                    "period_to": "2026-01-31",
                    "work_items": [
                        {
                            "name": "Бетонирование",
                            "unit": "м³",
                            "volume": 1,
                            "norm_hours": 1,
                            "price_per_unit": 1,
                        }
                    ],
                },
                headers={"X-API-Key": "valid-key"},
            )
    finally:
        generate._upsert_generated_doc = original_upsert
        settings.api_keys = old_keys

    assert response.status_code == 200
    data = response.json()
    assert data["total_cost"] == 60.0
    assert data["total_hours"] == 12.0

    mocked_process.assert_awaited_once()
    assert mocked_process.await_args.kwargs["intent"] == "generate_ks"
    assert captured_upsert["doc_id"] == mocked_process.await_args.kwargs["session_id"]
    assert captured_upsert["doc_type"] == "ks2"
    assert captured_upsert["payload"]["total_cost"] == 60.0
