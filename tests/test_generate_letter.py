"""Тесты /api/generate/letter."""

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from api.main import app
from api.routes import generate


def test_generate_letter_with_npa_pipeline():
    """POST /api/generate/letter с include_npa=True использует Legal Expert."""
    client = TestClient(app)
    mocked_process = AsyncMock(
        return_value={
            "session_id": "session-legal",
            "agents_used": [
                "researcher",
                "author",
                "legal_expert",
                "critic",
                "verifier",
                "formatter",
            ],
            "confidence": 0.93,
            "reply": "Итоговый текст письма",
            "state": {
                "docx_payload": {"title": "Письмо", "sections": []},
                "history": [
                    {
                        "agent_name": "LegalExpert",
                        "output": "Основания: ст. 309 ГК РФ; ФЗ-44.",
                    }
                ],
            },
        }
    )

    generate.orchestrator.process = mocked_process

    response = client.post(
        "/api/generate/letter",
        json={
            "letter_type": "запрос",
            "addressee": "ООО Ромашка",
            "subject": "Предоставление графика работ",
            "body_points": ["Просим прислать график", "Срок до 15.05.2026"],
            "contract_number": "Д-123",
            "include_npa": True,
            "role": "foreman",
            "session_id": "session-legal",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "session-legal"
    assert "legal_expert" in data["agents_used"]
    assert data["legal_references"] == ["ст. 309 ГК РФ", "ФЗ-44"]

    mocked_process.assert_awaited_once()
    call_kwargs = mocked_process.await_args.kwargs
    assert call_kwargs["intent"] == "generate_letter"
    assert call_kwargs["include_legal_expert"] is True
    assert "Тип: запрос." in call_kwargs["message"]


def test_generate_letter_without_npa_pipeline():
    """POST /api/generate/letter с include_npa=False отключает Legal Expert."""
    client = TestClient(app)
    mocked_process = AsyncMock(
        return_value={
            "session_id": "session-no-legal",
            "agents_used": ["researcher", "author", "critic", "verifier", "formatter"],
            "confidence": 0.9,
            "reply": "Итоговый текст письма",
            "state": {
                "docx_payload": {"title": "Письмо без НПА", "sections": []},
                "history": [],
            },
        }
    )

    generate.orchestrator.process = mocked_process

    response = client.post(
        "/api/generate/letter",
        json={
            "letter_type": "ответ",
            "addressee": "АО Заказчик",
            "subject": "Ответ по замечаниям",
            "body_points": ["Замечания устранены"],
            "include_npa": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "session-no-legal"
    assert "legal_expert" not in data["agents_used"]
    assert data["legal_references"] == []

    mocked_process.assert_awaited_once()
    call_kwargs = mocked_process.await_args.kwargs
    assert call_kwargs["intent"] == "generate_letter"
    assert call_kwargs["include_legal_expert"] is False
    assert "Договор: не указан." in call_kwargs["message"]
