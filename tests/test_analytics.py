"""Tests for analytics schedule prediction API."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app
from api.routes import analytics as analytics_routes
from api.routes.auth import _create_token


def _auth_headers(username: str = "analytics-user") -> dict[str, str]:
    token = _create_token(username, "pto_engineer")
    return {"Authorization": f"Bearer {token}"}


def test_predict_no_delays(monkeypatch):
    async def _mock_predict(project_id: str) -> dict:
        assert project_id == "project-1"
        return {
            "avg_delay_days": 0.0,
            "delay_rate": 0.0,
            "predicted_completion": "2026-05-20",
            "risks": [],
            "recommendations": ["Продолжать текущий темп"],
        }

    async def _cache_miss(_: str):
        return None

    async def _cache_set(_: str, __: str, ttl: int = 0):
        assert ttl == 21600

    monkeypatch.setattr(analytics_routes._predictor, "predict_completion", _mock_predict)
    monkeypatch.setattr(analytics_routes._cache, "get", _cache_miss)
    monkeypatch.setattr(analytics_routes._cache, "set", _cache_set)

    with TestClient(app) as client:
        response = client.get("/api/analytics/schedule/project-1", headers=_auth_headers())

    assert response.status_code == 200
    data = response.json()
    assert data["avg_delay_days"] == 0.0
    assert data["delay_rate"] == 0.0
    assert data["risks"] == []


def test_predict_with_delays(monkeypatch):
    async def _mock_predict(_: str) -> dict:
        return {
            "avg_delay_days": 4.5,
            "delay_rate": 0.3,
            "predicted_completion": "2026-06-10",
            "risks": [
                {
                    "section": "AR",
                    "description": "Срыв поставки фасадных материалов",
                    "severity": "high",
                }
            ],
            "recommendations": ["Ускорить закупки по разделу AR"],
        }

    async def _cache_miss(_: str):
        return None

    async def _cache_set(_: str, __: str, ttl: int = 0):
        assert ttl == 21600

    monkeypatch.setattr(analytics_routes._predictor, "predict_completion", _mock_predict)
    monkeypatch.setattr(analytics_routes._cache, "get", _cache_miss)
    monkeypatch.setattr(analytics_routes._cache, "set", _cache_set)

    with TestClient(app) as client:
        response = client.get("/api/analytics/schedule/project-42", headers=_auth_headers())

    assert response.status_code == 200
    data = response.json()
    assert data["delay_rate"] == 0.3
    assert data["risks"][0]["severity"] == "high"


def test_cache_hit(monkeypatch):
    calls = {"predict": 0}

    async def _mock_predict(_: str) -> dict:
        calls["predict"] += 1
        return {
            "avg_delay_days": 2.0,
            "delay_rate": 0.2,
            "predicted_completion": "2026-06-01",
            "risks": [],
            "recommendations": [],
        }

    class FakeCache:
        def __init__(self):
            self.data: dict[str, str] = {}

        async def get(self, key: str):
            return self.data.get(key)

        async def set(self, key: str, value: str, ttl: int = 0):
            self.data[key] = value

    fake_cache = FakeCache()
    monkeypatch.setattr(analytics_routes, "_cache", fake_cache)
    monkeypatch.setattr(analytics_routes._predictor, "predict_completion", _mock_predict)

    with TestClient(app) as client:
        first = client.get("/api/analytics/schedule/project-cache", headers=_auth_headers())
        second = client.get("/api/analytics/schedule/project-cache", headers=_auth_headers())

    assert first.status_code == 200
    assert second.status_code == 200
    assert calls["predict"] == 1
