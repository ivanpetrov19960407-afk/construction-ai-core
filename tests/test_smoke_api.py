"""Smoke test for API routes availability."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from api.main import app
from api.routes import generate, rag, sign
from core.cache import RedisCache
from config.settings import settings


class _FakeRagCollection:
    def get(self, include: list[str] | None = None) -> dict[str, list[Any]]:
        return {"ids": [], "metadatas": []}

    def delete(self, ids: list[str]) -> None:
        return None


class _FakeRagEngine:
    collection = _FakeRagCollection()

    def get_stats(self) -> dict[str, Any]:
        return {"total_chunks": 0, "sources": [], "last_updated": ""}


async def _cache_get(self: RedisCache, key: str) -> None:
    return None


async def _cache_set(self: RedisCache, key: str, value: str, ttl: int = 3600) -> None:
    return None


async def _cache_delete(self: RedisCache, key: str) -> None:
    return None


async def _cache_enqueue(self: RedisCache, queue: str, task: dict[str, Any]) -> bool:
    return False


async def _cache_dequeue(self: RedisCache, queue: str) -> None:
    return None


async def _fake_ks2_export(doc_id: str, org_id: str) -> bytes:
    return b"<xml/>"


async def _fake_m29_export(project_id: str, period: str | None = None) -> bytes:
    return b"<xml/>"


@pytest.fixture
def smoke_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Configure deterministic local test environment for smoke checks."""
    db_path = tmp_path / "smoke.sqlite"
    monkeypatch.setattr(settings, "sqlite_db_path", str(db_path))
    monkeypatch.setattr(settings, "jwt_secret", "smoke-secret-with-at-least-32-characters")
    monkeypatch.setattr(settings, "api_keys", ["smoke-key"])
    monkeypatch.setattr(settings, "admin_api_keys", ["smoke-key"])
    monkeypatch.setattr(settings, "redis_url", "redis://localhost:6379/0")
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))

    monkeypatch.setattr(rag, "get_rag_engine", lambda: _FakeRagEngine())
    monkeypatch.setattr(RedisCache, "get", _cache_get)
    monkeypatch.setattr(RedisCache, "set", _cache_set)
    monkeypatch.setattr(RedisCache, "delete", _cache_delete)
    monkeypatch.setattr(RedisCache, "enqueue", _cache_enqueue)
    monkeypatch.setattr(RedisCache, "dequeue", _cache_dequeue)
    monkeypatch.setattr(generate.onec_exporter, "export_ks2_to_xml", _fake_ks2_export)
    monkeypatch.setattr(generate.onec_exporter, "export_m29_to_xml", _fake_m29_export)
    monkeypatch.setattr(sign, "_fetch_exec_doc_for_verify", lambda doc_id, org_id="default": None)


def _iter_http_routes() -> Iterable[APIRoute]:
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.path in {"/docs", "/redoc", "/openapi.json"}:
            continue
        yield route


def _path_value(name: str, annotation: Any) -> str:
    if annotation in {int}:
        return "stub"
    if annotation in {float}:
        return "1.0"
    if annotation in {UUID}:
        return "00000000-0000-0000-0000-000000000001"
    return "stub"


def _build_path(route: APIRoute) -> str:
    path = route.path
    for param in route.dependant.path_params:
        placeholder = "{" + param.name
        if placeholder not in path:
            continue
        annotation = getattr(param, "type_", None) or getattr(param, "annotation", str)
        value = _path_value(param.name, annotation)
        path = path.replace("{" + param.name + "}", value)
        path = path.replace("{" + param.name + ":path}", value)
        path = path.replace("{" + param.name + ":str}", value)
        path = path.replace("{" + param.name + ":int}", value)
    return path


def test_smoke_get_post_routes_not_500(smoke_env: None) -> None:
    """Every GET/POST HTTP route should respond with a non-500 status."""
    with TestClient(app, raise_server_exceptions=False) as client:
        for route in _iter_http_routes():
            methods = sorted(route.methods or set())
            for method in methods:
                if method not in {"GET", "POST"}:
                    continue

                url = _build_path(route)
                headers = {"X-API-Key": "smoke-key"}
                if method == "GET":
                    response = client.get(url, headers=headers)
                else:
                    response = client.post(url, headers=headers, json={})

                assert response.status_code != 500, f"{method} {route.path} -> {response.status_code}"
