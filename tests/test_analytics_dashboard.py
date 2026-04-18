"""Tests for all-project analytics dashboard and predictor fast path."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from fastapi.testclient import TestClient

from api.main import app
from api.routes import analytics as analytics_routes
from api.routes.auth import _create_token
from config.settings import settings
from core.analytics.schedule_predictor import SchedulePredictor


@dataclass
class _FakeProject:
    id: str
    name: str


class _FakeScalars:
    def __init__(self, rows: list[_FakeProject]):
        self._rows = rows

    def all(self) -> list[_FakeProject]:
        return self._rows


class _FakeExecuteResult:
    def __init__(self, rows: list[_FakeProject]):
        self._rows = rows

    def scalars(self) -> _FakeScalars:
        return _FakeScalars(self._rows)


class _FakeSession:
    def __init__(self, rows: list[_FakeProject]):
        self._rows = rows

    def __enter__(self) -> _FakeSession:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        _ = (exc_type, exc, tb)

    def execute(self, _stmt):
        return _FakeExecuteResult(self._rows)


class _FakeSessionMaker:
    def __init__(self, rows: list[_FakeProject]):
        self._rows = rows

    def __call__(self) -> _FakeSession:
        return _FakeSession(self._rows)


def _auth_headers(username: str = "analytics-user") -> dict[str, str]:
    token = _create_token(username, "pto_engineer")
    return {"Authorization": f"Bearer {token}"}


def _dashboard_response(
    monkeypatch,
    rows: list[_FakeProject],
    predictions: dict[str, dict],
    threshold: float = 0.3,
):
    async def _mock_predict(project_id: str, *, include_llm: bool = True) -> dict:
        assert include_llm is False
        return predictions[project_id]

    monkeypatch.setattr(
        analytics_routes,
        "get_projects_sessionmaker",
        lambda _db_path: _FakeSessionMaker(rows),
    )
    monkeypatch.setattr(analytics_routes._predictor, "predict_completion", _mock_predict)

    with TestClient(app) as client:
        return client.get(
            f"/api/analytics/dashboard/all?threshold={threshold}",
            headers=_auth_headers(),
        )


def test_all_dashboard_empty_db(monkeypatch):
    response = _dashboard_response(monkeypatch, rows=[], predictions={})

    assert response.status_code == 200
    data = response.json()
    assert data["high_risk_projects"] == []
    assert data["total_checked"] == 0
    assert data["threshold"] == 0.3


def test_all_dashboard_filters_low_risk(monkeypatch):
    response = _dashboard_response(
        monkeypatch,
        rows=[_FakeProject(id="project_1", name="One"), _FakeProject(id="project_2", name="Two")],
        predictions={
            "project_1": {
                "delay_rate": 0.5,
                "avg_delay_days": 4,
                "predicted_completion": "2026-06-01",
                "risks": [],
            },
            "project_2": {
                "delay_rate": 0.1,
                "avg_delay_days": 1,
                "predicted_completion": "2026-05-20",
                "risks": [],
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["high_risk_projects"]) == 1
    assert data["high_risk_projects"][0]["project_id"] == "project_1"


def test_all_dashboard_sorted_by_delay_rate(monkeypatch):
    response = _dashboard_response(
        monkeypatch,
        rows=[
            _FakeProject(id="project_1", name="One"),
            _FakeProject(id="project_2", name="Two"),
            _FakeProject(id="project_3", name="Three"),
        ],
        predictions={
            "project_1": {
                "delay_rate": 0.4,
                "avg_delay_days": 4,
                "predicted_completion": "2026-06-01",
                "risks": [],
            },
            "project_2": {
                "delay_rate": 0.9,
                "avg_delay_days": 8,
                "predicted_completion": "2026-08-01",
                "risks": [],
            },
            "project_3": {
                "delay_rate": 0.5,
                "avg_delay_days": 5,
                "predicted_completion": "2026-07-01",
                "risks": [],
            },
        },
    )

    assert response.status_code == 200
    projects = response.json()["high_risk_projects"]
    assert [item["project_id"] for item in projects] == ["project_2", "project_3", "project_1"]


def test_all_dashboard_custom_threshold(monkeypatch):
    response = _dashboard_response(
        monkeypatch,
        rows=[_FakeProject(id="project_1", name="One"), _FakeProject(id="project_2", name="Two")],
        predictions={
            "project_1": {
                "delay_rate": 0.79,
                "avg_delay_days": 5,
                "predicted_completion": "2026-06-20",
                "risks": [],
            },
            "project_2": {
                "delay_rate": 0.8,
                "avg_delay_days": 6,
                "predicted_completion": "2026-06-25",
                "risks": [],
            },
        },
        threshold=0.8,
    )

    assert response.status_code == 200
    projects = response.json()["high_risk_projects"]
    assert [item["project_id"] for item in projects] == ["project_2"]


def test_predict_completion_include_llm_false(monkeypatch, tmp_path):
    old_path = settings.sqlite_db_path
    settings.sqlite_db_path = str(tmp_path / "analytics_predictor.db")

    predictor = SchedulePredictor()
    calls = {"llm": 0}

    async def _mock_history(_project_id: str) -> list[dict]:
        return []

    async def _mock_open_tasks(_project_id: str) -> list[dict]:
        return [{"planned_finish": "2026-06-01"}]

    async def _mock_project_name(_project_id: str) -> str:
        return "Demo"

    async def _mock_llm(*_args, **_kwargs) -> dict:
        calls["llm"] += 1
        return {"predicted_completion": "2026-12-31", "risks": [], "recommendations": []}

    monkeypatch.setattr(predictor, "get_project_history", _mock_history)
    monkeypatch.setattr(predictor, "_get_open_tasks", _mock_open_tasks)
    monkeypatch.setattr(predictor, "_get_project_name", _mock_project_name)
    monkeypatch.setattr(predictor, "_llm_assessment", _mock_llm)

    try:
        result = asyncio.run(predictor.predict_completion("project_1", include_llm=False))
    finally:
        settings.sqlite_db_path = old_path

    assert calls["llm"] == 0
    assert result["predicted_completion"] == "2026-06-01"
    assert result["risks"] == []
    assert result["recommendations"] == []
