import asyncio

import pytest

from agents.researcher.agent import ResearcherAgent
from agents.researcher.config import ResearcherConfig
from agents.researcher.errors import ResearchAccessError, ResearchScopeError
from agents.researcher.source_collector import SourceCollector


class _Router:
    async def query(self, prompt: str, system_prompt: str):
        class _Resp:
            text = '{"facts": [], "gaps": []}'

        return _Resp()


class _Rag:
    def __init__(self):
        self.last_kwargs = None

    async def search(self, query: str, **kwargs):
        self.last_kwargs = kwargs
        return [
            {
                "source": "doc",
                "page": 1,
                "text": "quote",
                "score": 0.9,
                "tenant_id": kwargs.get("tenant_id"),
                "org_id": kwargs.get("org_id"),
                "project_id": kwargs.get("project_id"),
                "user_id": kwargs.get("user_id"),
            }
        ]


class _Web:
    async def run(self, query: str, max_results: int):
        return []


def test_unknown_scope_fails() -> None:
    with pytest.raises(ResearchScopeError):
        ResearcherAgent._validate_access_scope("admin")


def test_empty_scope_fails() -> None:
    with pytest.raises(ResearchScopeError):
        ResearcherAgent._resolve_access_scope({"access_scope": ""})


def test_private_scope_without_user_id_fails() -> None:
    collector = SourceCollector(_Rag(), _Web(), None, ResearcherConfig())  # type: ignore[arg-type]
    with pytest.raises(ResearchAccessError):
        asyncio.run(collector.collect("q", topic_scope=None, access_scope="private", context=""))


def test_tenant_scope_without_tenant_id_fails() -> None:
    collector = SourceCollector(_Rag(), _Web(), None, ResearcherConfig())  # type: ignore[arg-type]
    with pytest.raises(ResearchAccessError):
        asyncio.run(collector.collect("q", topic_scope=None, access_scope="tenant", context=""))


def test_project_scope_without_project_id_and_tenant_id_fails() -> None:
    collector = SourceCollector(_Rag(), _Web(), None, ResearcherConfig())  # type: ignore[arg-type]
    with pytest.raises(ResearchAccessError):
        asyncio.run(
            collector.collect(
                "q",
                topic_scope=None,
                access_scope="project",
                context="",
                tenant_id="t1",
            )
        )


def test_rag_engine_receives_identity_filters() -> None:
    rag = _Rag()
    collector = SourceCollector(rag, _Web(), None, ResearcherConfig())  # type: ignore[arg-type]
    asyncio.run(
        collector.collect(
            "q",
            topic_scope=None,
            access_scope="tenant",
            context="",
            tenant_id="t1",
            org_id="o1",
            project_id="p1",
            user_id="u1",
        )
    )
    assert rag.last_kwargs["filter_scope"] == "tenant"
    assert rag.last_kwargs["tenant_id"] == "t1"
    assert rag.last_kwargs["org_id"] == "o1"
    assert rag.last_kwargs["project_id"] == "p1"
    assert rag.last_kwargs["user_id"] == "u1"


def test_legacy_role_does_not_fallback_to_public() -> None:
    with pytest.raises(ResearchScopeError):
        ResearcherAgent._resolve_access_scope({"role": "admin"})
