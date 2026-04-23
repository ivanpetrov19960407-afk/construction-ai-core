"""Unit-тесты ResearcherAgent."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from agents.researcher import ResearcherAgent
from config.settings import settings
from schemas.research import ResearchFact, ResearchSource


class _FakeCache:
    def __init__(self, get_side_effect: Exception | None = None) -> None:
        self.get_side_effect = get_side_effect
        self.set_calls = 0

    async def get(self, key: str) -> str | None:
        if self.get_side_effect:
            raise self.get_side_effect
        return None

    async def set(self, key: str, value: str, ttl: int = 3600) -> None:
        self.set_calls += 1


class _FakeRAGEngine:
    def __init__(self, search_impl: Any) -> None:
        self.search = search_impl


def _mock_llm_router(reply: str = "{}", side_effect: Exception | None = None) -> SimpleNamespace:
    query = AsyncMock()
    if side_effect is not None:
        query.side_effect = side_effect
    else:
        query.return_value = SimpleNamespace(text=reply)
    return SimpleNamespace(query=query)


def _mk_agent(
    *,
    llm_reply: str = "{}",
    llm_side_effect: Exception | None = None,
    rag_engine: Any | None = None,
    web_search_tool: Any | None = None,
    cache: Any | None = None,
) -> ResearcherAgent:
    return ResearcherAgent(
        cast(Any, _mock_llm_router(llm_reply, llm_side_effect)),
        rag_engine=cast(Any, rag_engine),
        web_search_tool=cast(Any, web_search_tool),
        cache=cast(Any, cache),
    )


def _source_rag_0(score: float = 0.7, snippet: str = "snippet") -> ResearchSource:
    return ResearchSource(
        id="rag-0",
        type="rag",
        title="СП",
        document="СП",
        page=1,
        score=score,
        snippet=snippet,
    )


@pytest.mark.parametrize(
    ("raw", "expected_facts_len", "expect_diag"),
    [
        (
            '{"facts":[{"text":"f","applicability":"high",'
            '"confidence":0.8,"source_ids":["rag-0"]}],"gaps":[]}',
            1,
            False,
        ),
        (
            "```json\n"
            '{"facts":[{"text":"f","applicability":"high",'
            '"confidence":0.8,"source_ids":["rag-0"]}],"gaps":[]}\n'
            "```",
            1,
            False,
        ),
        (
            "preamble {not json}\n"
            '{"facts":[{"text":"f","applicability":"high",'
            '"confidence":0.8,"source_ids":["rag-0"]}],"gaps":[]}\n'
            "epilogue",
            1,
            False,
        ),
        (
            '{"facts":[{"text":"f","applicability":"high",'
            '"confidence":0.8,"source_ids":["rag-0"]}],"gaps":["g1"]} trailing text',
            1,
            False,
        ),
        (
            '{"facts":[{"text":"f","applicability":"high","confidence":0.8,'
            '"source_ids":["rag-0"]}],"gaps":["outer"],'
            '"nested":{"inner":[{"x":1}]}}',
            1,
            False,
        ),
        ("totally invalid", 0, True),
    ],
)
def test_parse_llm_json_variants(raw: str, expected_facts_len: int, expect_diag: bool) -> None:
    agent = _mk_agent()
    payload = agent._parse_llm_json("query", raw, [_source_rag_0()])

    assert len(payload.facts) == expected_facts_len
    if expect_diag:
        assert "llm_invalid_json" in payload.diagnostics
    else:
        assert "llm_invalid_json" not in payload.diagnostics


def test_validate_fact_source_ids() -> None:
    facts = [
        ResearchFact(text="ok", applicability="", confidence=0.7, source_ids=["rag-0", "missing"]),
        ResearchFact(text="drop", applicability="", confidence=0.6, source_ids=["missing"]),
    ]
    sources = [_source_rag_0()]

    valid_facts, diagnostics = ResearcherAgent._validate_fact_source_ids(facts, sources)

    assert len(valid_facts) == 1
    assert valid_facts[0].source_ids == ["rag-0"]
    assert any("удалены невалидные" in d for d in diagnostics)
    assert any("отброшен" in d for d in diagnostics)


def test_need_web_fallback_thresholds_and_boundaries(monkeypatch: pytest.MonkeyPatch) -> None:
    agent = _mk_agent()
    monkeypatch.setattr(settings, "research_web_min_rag_sources", 2)
    monkeypatch.setattr(settings, "research_web_min_avg_score", 0.5)
    monkeypatch.setattr(settings, "research_web_min_snippet_chars", 10)

    assert agent._need_web_fallback([_source_rag_0(score=0.9, snippet="x" * 20)])

    low_avg = [
        _source_rag_0(score=0.4, snippet="x" * 6),
        ResearchSource(
            id="rag-1", type="rag", title="СП2", document="СП2", page=2, score=0.4, snippet="x" * 6
        ),
    ]
    assert agent._need_web_fallback(low_avg)

    low_snippet = [
        _source_rag_0(score=0.8, snippet="x" * 4),
        ResearchSource(
            id="rag-1", type="rag", title="СП2", document="СП2", page=2, score=0.8, snippet="x" * 4
        ),
    ]
    assert agent._need_web_fallback(low_snippet)

    boundary_ok = [
        _source_rag_0(score=0.5, snippet="x" * 5),
        ResearchSource(
            id="rag-1", type="rag", title="СП2", document="СП2", page=2, score=0.5, snippet="x" * 5
        ),
    ]
    assert not agent._need_web_fallback(boundary_ok)


def test_normalize_rag_score_similarity_and_distance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "rag_score_mode", "similarity")

    assert ResearcherAgent._normalize_rag_score({"score": 75}) == pytest.approx(0.75)
    assert ResearcherAgent._normalize_rag_score({"score": -10}) == pytest.approx(0.0)
    assert ResearcherAgent._normalize_rag_score(
        {"score": 0.2, "score_type": "distance"}
    ) == pytest.approx(0.8)
    assert ResearcherAgent._normalize_rag_score(
        {"score": 4.0, "score_type": "distance"}
    ) == pytest.approx(0.2)


def test_deduplicate_rag_sources() -> None:
    sources = [
        ResearchSource(
            id="rag-0", type="rag", title="СП 1", document="СП 1", page=5, score=0.6, snippet="a"
        ),
        ResearchSource(
            id="rag-1", type="rag", title="СП 1", document="СП 1", page=5, score=0.9, snippet="bb"
        ),
        ResearchSource(
            id="rag-2", type="rag", title="СП 2", document="СП 2", page=1, score=0.5, snippet="c"
        ),
    ]

    deduped = ResearcherAgent._deduplicate_rag_sources(sources)

    assert len(deduped) == 2
    assert any(item.document == "СП 1" and item.score == pytest.approx(0.9) for item in deduped)
    assert any(item.document == "СП 2" for item in deduped)


def test_llm_timeout_sets_diagnostics_and_state_keys() -> None:
    async def rag_search(
        query: str, n_results: int = 5, filter_scope: str | None = None
    ) -> list[dict[str, Any]]:
        return [{"source": "СП", "page": 1, "text": "t", "score": 0.8}]

    agent = _mk_agent(
        llm_side_effect=TimeoutError(),
        rag_engine=_FakeRAGEngine(rag_search),
        web_search_tool=SimpleNamespace(run=AsyncMock(return_value=[])),
        cache=_FakeCache(),
    )

    result = asyncio.run(agent.run({"message": "q", "history": []}))

    assert result["research_facts"] == "[]"
    payload = result["research_payload"]
    assert "llm_timeout" in payload["diagnostics"]
    assert "llm_invalid_json" not in payload["diagnostics"]
    assert "research_facts" in result
    assert "research_payload" in result


def test_rag_timeout_falls_back_to_web_and_keeps_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def slow_search(
        query: str, n_results: int = 5, filter_scope: str | None = None
    ) -> list[dict[str, Any]]:
        await asyncio.sleep(0.02)
        return [{"source": "СП", "page": 1, "text": "t", "score": 0.8}]

    web_tool = SimpleNamespace(
        run=AsyncMock(
            return_value=[{"title": "w", "url": "https://x", "snippet": "abc", "score": 0.5}]
        )
    )

    agent = _mk_agent(
        llm_reply='{"facts":[],"gaps":[]}',
        rag_engine=_FakeRAGEngine(slow_search),
        web_search_tool=web_tool,
        cache=_FakeCache(),
    )
    _ = monkeypatch
    agent._config.rag_timeout_seconds = 0.001

    sources, diagnostics, cache_hit = asyncio.run(
        agent._collect_sources(
            "q",
            topic_scope=None,
            access_scope=None,
            context="",
        )
    )

    assert any(source.type == "web" for source in sources)
    assert any(item.startswith("rag_failed") or item == "rag_timeout" for item in diagnostics)
    assert cache_hit is False


def test_cache_failure_does_not_break_agent() -> None:
    async def rag_search(
        query: str, n_results: int = 5, filter_scope: str | None = None
    ) -> list[dict[str, Any]]:
        return [{"source": "СП", "page": 1, "text": "t", "score": 0.8}]

    agent = _mk_agent(
        llm_reply='{"facts":[],"gaps":[]}',
        rag_engine=_FakeRAGEngine(rag_search),
        web_search_tool=SimpleNamespace(run=AsyncMock(return_value=[])),
        cache=_FakeCache(get_side_effect=ConnectionError("redis down")),
    )

    result = asyncio.run(agent.run({"message": "q", "history": []}))
    diagnostics = result["research_payload"]["diagnostics"]

    assert "cache_unavailable" in diagnostics
    assert "research_payload" in result


def test_compute_confidence_overall_edge_cases() -> None:
    fact = ResearchFact(text="f", applicability="", confidence=0.9, source_ids=["rag-0"])
    source = _source_rag_0(score=0.8)

    both = ResearcherAgent._compute_confidence_overall([fact], [source])
    only_sources = ResearcherAgent._compute_confidence_overall([], [source])
    only_facts = ResearcherAgent._compute_confidence_overall([fact], [])
    empty = ResearcherAgent._compute_confidence_overall([], [])

    assert both == pytest.approx(0.86)
    assert only_sources == pytest.approx(0.32)
    assert only_facts == pytest.approx(0.54)
    assert empty == pytest.approx(0.0)


def test_collection_diagnostics_are_merged_and_deduplicated() -> None:
    agent = _mk_agent(llm_reply='{"facts":[],"gaps":["g1","g1"]}')
    agent._collect_sources = AsyncMock(
        return_value=([], ["cache_unavailable", "cache_unavailable"], False)
    )  # type: ignore[method-assign]

    result = asyncio.run(agent.run({"message": "q", "history": []}))
    payload = result["research_payload"]

    assert payload["diagnostics"][0] == "cache_unavailable"
    assert payload["diagnostics"].count("cache_unavailable") == 1
    assert payload["gaps"].count("g1") == 1
