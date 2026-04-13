"""Тесты /api/generate/tk."""

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from api.main import app
from api.routes import generate


def test_generate_tk_happy_path():
    """POST /api/generate/tk возвращает TKResponse при успешной обработке."""
    client = TestClient(app)
    mocked_process = AsyncMock(
        return_value={
            "session_id": "session-1",
            "agents_used": ["researcher", "author", "critic", "verifier", "formatter"],
            "confidence": 0.96,
            "sha256": "abc123",
            "state": {"docx_payload": {"title": "ТК", "sections": []}},
        }
    )

    generate.orchestrator.process = mocked_process

    response = client.post(
        "/api/generate/tk",
        json={
            "work_type": "бетонирование монолитных конструкций",
            "object_name": "ЖК Север",
            "volume": 120.5,
            "unit": "м³",
            "norms": ["СП 70.13330", "ГОСТ 7473"],
            "role": "pto_engineer",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "session-1"
    assert data["agents_used"][-1] == "formatter"
    assert data["document"]["title"] == "ТК"
    mocked_process.assert_awaited_once()
    call_kwargs = mocked_process.await_args.kwargs
    assert call_kwargs["intent"] == "generate_tk"
    assert call_kwargs["role"] == "pto_engineer"
    assert "бетонирование монолитных конструкций" in call_kwargs["message"]


def test_generate_tk_validation_error():
    """POST /api/generate/tk должен вернуть 422 при невалидных данных."""
    client = TestClient(app)

    response = client.post(
        "/api/generate/tk",
        json={
            "work_type": "бетон",
            "object_name": "ЖК Север",
            "volume": 0,
            "unit": "литр",
        },
    )

    assert response.status_code == 422
