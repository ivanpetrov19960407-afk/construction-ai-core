"""Unit-тесты чистых функций ResearcherAgent."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from agents.researcher import ResearcherAgent
from schemas.research import ResearchFact, ResearchSource


def _mock_llm_router(reply: str = "{}") -> SimpleNamespace:
    return SimpleNamespace(query=AsyncMock(return_value=SimpleNamespace(text=reply)))


def _mk_agent() -> ResearcherAgent:
    return ResearcherAgent(cast(Any, _mock_llm_router()))


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
            "before text\n"
            '{"facts":[{"text":"f","applicability":"high",'
            '"confidence":0.8,"source_ids":["rag-0"]}],"gaps":[]}\n'
            "after text",
            1,
            False,
        ),
        (
            '{"facts":[{"text":"f","applicability":"high",'
            '"confidence":0.8,"source_ids":["rag-0"]}],"gaps":[]} trailing',
            1,
            False,
        ),
        ("totally invalid", 0, True),
    ],
)
def test_parse_llm_json_variants(raw: str, expected_facts_len: int, expect_diag: bool) -> None:
    agent = _mk_agent()
    sources = [
        ResearchSource(
            id="rag-0",
            type="rag",
            title="СП",
            document="СП",
            page=1,
            score=0.7,
            snippet="snippet",
        )
    ]

    payload = agent._parse_llm_json("query", raw, sources)

    assert len(payload.facts) == expected_facts_len
    if expect_diag:
        assert "LLM вернул ответ не в JSON-формате" in payload.diagnostics
    else:
        assert "LLM вернул ответ не в JSON-формате" not in payload.diagnostics


def test_validate_fact_source_ids() -> None:
    facts = [
        ResearchFact(text="ok", applicability="", confidence=0.7, source_ids=["rag-0", "missing"]),
        ResearchFact(text="drop", applicability="", confidence=0.6, source_ids=["missing"]),
    ]
    sources = [ResearchSource(id="rag-0", type="rag", title="S", score=0.8)]

    valid_facts, diagnostics = ResearcherAgent._validate_fact_source_ids(facts, sources)

    assert len(valid_facts) == 1
    assert valid_facts[0].source_ids == ["rag-0"]
    assert any("удалены невалидные" in d for d in diagnostics)
    assert any("отброшен" in d for d in diagnostics)


def test_need_web_fallback_thresholds() -> None:
    agent = _mk_agent()
    low = [ResearchSource(id="rag-0", type="rag", title="S", score=0.2, snippet="x" * 800)]
    assert agent._need_web_fallback(low)

    enough = [
        ResearchSource(id="rag-0", type="rag", title="A", score=0.8, snippet="x" * 300),
        ResearchSource(id="rag-1", type="rag", title="B", score=0.7, snippet="x" * 300),
    ]
    assert not agent._need_web_fallback(enough)


def test_normalize_rag_score_similarity_and_distance() -> None:
    similarity_chunk = {"score": 0.75, "score_type": "similarity"}
    distance_chunk_unit = {"score": 0.2, "score_type": "distance"}
    distance_chunk_large = {"score": 4.0, "score_type": "distance"}

    assert ResearcherAgent._normalize_rag_score(similarity_chunk) == pytest.approx(0.75)
    assert ResearcherAgent._normalize_rag_score(distance_chunk_unit) == pytest.approx(0.8)
    assert ResearcherAgent._normalize_rag_score(distance_chunk_large) == pytest.approx(0.2)


def test_deduplicate_rag_sources() -> None:
    sources = [
        ResearchSource(
            id="rag-0",
            type="rag",
            title="СП 1",
            document="СП 1",
            page=5,
            score=0.6,
            snippet="a",
        ),
        ResearchSource(
            id="rag-1",
            type="rag",
            title="СП 1",
            document="СП 1",
            page=5,
            score=0.9,
            snippet="bb",
        ),
        ResearchSource(
            id="rag-2",
            type="rag",
            title="СП 2",
            document="СП 2",
            page=1,
            score=0.5,
            snippet="c",
        ),
    ]

    deduped = ResearcherAgent._deduplicate_rag_sources(sources)

    assert len(deduped) == 2
    assert any(item.document == "СП 1" and item.score == pytest.approx(0.9) for item in deduped)
    assert any(item.document == "СП 2" for item in deduped)
