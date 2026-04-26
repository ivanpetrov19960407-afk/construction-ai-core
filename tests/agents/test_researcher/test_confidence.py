from agents.researcher.confidence import ConfidenceScorer
from agents.researcher.config import ResearcherConfig
from schemas.research import ResearchEvidence, ResearchFact, ResearchSource


def test_unsupported_facts_lower_score() -> None:
    cfg = ResearcherConfig()
    facts = [ResearchFact(text="x", source_ids=["s1"], support_status="unsupported")]
    sources = [ResearchSource(id="s1", type="rag", title="doc", score=0.9)]
    res = ConfidenceScorer.score(facts, sources, cfg)
    assert res.overall < 0.6


def test_fake_citations_lower_score() -> None:
    cfg = ResearcherConfig()
    facts = [ResearchFact(text="x", source_ids=["missing"], support_status="supported")]
    res = ConfidenceScorer.score(facts, [], cfg)
    assert res.overall < 0.5


def test_multiple_independent_sources_increase_score() -> None:
    cfg = ResearcherConfig()
    facts = [
        ResearchFact(
            text="x",
            source_ids=["s1", "s2"],
            support_status="supported",
            evidence=[
                ResearchEvidence(source_id="s1", quote="x", support_status="supported"),
                ResearchEvidence(source_id="s2", quote="x", support_status="supported"),
            ],
        )
    ]
    sources = [
        ResearchSource(id="s1", type="rag", title="a", score=0.8),
        ResearchSource(id="s2", type="rag", title="b", score=0.8),
    ]
    res = ConfidenceScorer.score(facts, sources, cfg)
    assert res.independent_sources > 0.8


def test_stale_source_lowers_score() -> None:
    cfg = ResearcherConfig()
    facts = [
        ResearchFact(
            text="x",
            source_ids=["s1"],
            support_status="supported",
            evidence=[ResearchEvidence(source_id="s1", quote="x", support_status="supported")],
        )
    ]
    sources = [ResearchSource(id="s1", type="rag", title="a", score=0.9, is_active=False)]
    res = ConfidenceScorer.score(facts, sources, cfg)
    assert res.source_currency_score < 1.0


def test_llm_self_confidence_does_not_inflate_score() -> None:
    cfg = ResearcherConfig()
    facts = [ResearchFact(text="x", confidence=1.0, source_ids=[])]
    res = ConfidenceScorer.score(facts, [], cfg)
    assert res.llm_self_reported_confidence == 0.0
    assert res.overall < 0.5
