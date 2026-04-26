import asyncio
import json

import pytest

from agents.researcher.agent import ResearcherAgent
from agents.researcher.confidence import ConfidenceScorer
from agents.researcher.config import ResearcherConfig
from agents.researcher.fact_validator import FactValidator
from agents.researcher.llm_client import StructuredLLMClient
from agents.researcher.source_collector import SourceCollector
from schemas.research import ResearchEvidence, ResearchFact, ResearchSource


class _Resp:
    def __init__(self, text: str) -> None:
        self.text = text


class _Router:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls = 0

    async def query(self, prompt: str, system_prompt: str):
        _ = (prompt, system_prompt)
        self.calls += 1
        idx = min(self.calls - 1, len(self.responses) - 1)
        return _Resp(self.responses[idx])


class _Web:
    def __init__(self) -> None:
        self.calls = 0

    async def run(self, query: str, max_results: int):
        self.calls += 1
        _ = (query, max_results)
        return [{"title": "web", "url": "https://example.com", "snippet": "w", "score": 0.2}]


class _RagWeak:
    supports_identity_filters = True

    def validate_identity_filter_support(self) -> None:
        return None

    async def search(self, query: str, **kwargs):
        _ = (query, kwargs)
        return [
            {
                "source": "doc",
                "text": "small",
                "score": 0.1,
                "tenant_id": kwargs.get("tenant_id"),
                "org_id": kwargs.get("org_id"),
                "project_id": kwargs.get("project_id"),
                "user_id": kwargs.get("user_id"),
            }
        ]


class _RagStrong:
    supports_identity_filters = True

    def validate_identity_filter_support(self) -> None:
        return None

    async def search(self, query: str, **kwargs):
        _ = (query, kwargs)
        return [
            {
                "source": "СП 63",
                "text": "должен",
                "score": 0.95,
                "is_active": True,
                "source_type": "norm",
            }
        ]


@pytest.mark.parametrize(
    "scope,kwargs",
    [
        ("private", {"user_id": "u1"}),
        ("tenant", {"tenant_id": "t1"}),
        ("project", {"tenant_id": "t1", "project_id": "p1"}),
    ],
)
def test_non_public_scope_never_calls_web(scope: str, kwargs: dict[str, str]) -> None:
    web = _Web()
    collector = SourceCollector(_RagWeak(), web, None, ResearcherConfig(web_min_rag_sources=5))  # type: ignore[arg-type]
    _, diags, _ = asyncio.run(
        collector.collect("q", topic_scope=None, access_scope=scope, context="", **kwargs)
    )
    assert web.calls == 0
    assert any(d.code == "web_fallback_blocked_private_scope" for d in diags)


def test_public_weak_rag_calls_web_and_public_strong_does_not() -> None:
    web = _Web()
    weak = SourceCollector(_RagWeak(), web, None, ResearcherConfig(web_min_rag_sources=5))  # type: ignore[arg-type]
    asyncio.run(weak.collect("q", topic_scope=None, access_scope="public", context=""))
    assert web.calls == 1

    web2 = _Web()
    strong = SourceCollector(
        _RagStrong(),
        web2,
        None,
        ResearcherConfig(web_min_rag_sources=1, web_min_avg_score=0.001),
    )  # type: ignore[arg-type]
    asyncio.run(strong.collect("q", topic_scope=None, access_scope="public", context=""))
    assert web2.calls == 0


def test_rag_metadata_flows_to_source() -> None:
    class _RagMeta(_RagStrong):
        async def search(self, query: str, **kwargs):
            _ = (query, kwargs)
            return [
                {
                    "source": "СП",
                    "text": "full chunk text",
                    "chunk_text": "full chunk text",
                    "score": 0.8,
                    "document_id": "d1",
                    "chunk_id": "c1",
                    "jurisdiction": "RU",
                    "document_version": "2025",
                    "is_active": True,
                }
            ]

    collector = SourceCollector(_RagMeta(), _Web(), None, ResearcherConfig())  # type: ignore[arg-type]
    sources, _, _ = asyncio.run(
        collector.collect("q", topic_scope=None, access_scope="public", context="")
    )
    assert sources[0].document_id == "d1"
    assert sources[0].chunk_id == "c1"
    assert sources[0].jurisdiction == "RU"
    assert sources[0].chunk_text == "full chunk text"


def test_fact_quote_found_but_not_entailing() -> None:
    facts = [
        ResearchFact(
            text="По ГОСТ требуется обязательность",
            source_ids=["s1"],
            evidence=[ResearchEvidence(source_id="s1", quote="Класс бетона B30")],
        )
    ]
    sources = [ResearchSource(id="s1", type="rag", title="СП", snippet="Класс бетона B30")]
    validated, _ = FactValidator.validate(facts, sources)
    assert validated[0].support_status in {
        "quote_found_but_not_entailing",
        "partially_supported",
    }


def test_two_chunks_same_document_not_independent() -> None:
    facts = [
        ResearchFact(
            text="x",
            source_ids=["s1", "s2"],
            evidence=[
                ResearchEvidence(source_id="s1", quote="x", support_status="supported"),
                ResearchEvidence(source_id="s2", quote="x", support_status="supported"),
            ],
            support_status="supported",
        )
    ]
    sources = [
        ResearchSource(
            id="s1",
            type="rag",
            title="doc",
            document_id="doc1",
            authority="A",
            score=0.8,
        ),
        ResearchSource(
            id="s2",
            type="rag",
            title="doc",
            document_id="doc1",
            authority="A",
            score=0.8,
        ),
    ]
    score = ConfidenceScorer.score(facts, sources, ResearcherConfig())
    assert score.independent_sources < 0.7


def test_llm_nested_extra_rejected() -> None:
    payload = json.dumps(
        {
            "facts": [
                {
                    "text": "x",
                    "source_ids": [],
                    "evidence": [{"source_id": "s1", "quote": "q", "evil": 1}],
                }
            ],
            "gaps": [],
        },
        ensure_ascii=False,
    )
    client = StructuredLLMClient(_Router([payload]), ResearcherConfig())  # type: ignore[arg-type]
    with pytest.raises(Exception):
        asyncio.run(client.query("p", "s"))


def test_public_payload_redacts_access_ids() -> None:
    router = _Router(['{"facts": [], "gaps": []}'])
    agent = ResearcherAgent(
        llm_router=router,
        rag_engine=_RagStrong(),
        web_search_tool=_Web(),
        cache=None,
        config=ResearcherConfig(),
    )  # type: ignore[arg-type]
    state = {"message": "q", "access_scope": "tenant", "tenant_id": "t1", "context": ""}
    out = asyncio.run(agent._run(state))
    sources = out["research_payload"]["sources"]
    for src in sources:
        assert src.get("tenant_id") is None
        assert src.get("org_id") is None
        assert src.get("project_id") is None
        assert src.get("user_id") is None
