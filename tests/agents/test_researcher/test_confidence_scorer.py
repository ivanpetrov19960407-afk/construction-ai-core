from agents.researcher.confidence import ConfidenceScorer
from agents.researcher.config import ResearcherConfig
from schemas.research import ResearchEvidence, ResearchFact, ResearchSource


def _supported_fact(source_id: str, *, status: str = "supported") -> ResearchFact:
    return ResearchFact(
        text="x",
        source_ids=[source_id],
        support_status=status,
        evidence=[ResearchEvidence(source_id=source_id, quote="x", support_status=status)],
    )


def test_unsupported_facts_score_zero() -> None:
    cfg = ResearcherConfig()
    fact = ResearchFact(text="x", source_ids=["s1"], support_status="unsupported")
    sources = [ResearchSource(id="s1", type="rag", title="doc", score=0.8)]
    result = ConfidenceScorer.score([fact], sources, cfg)
    assert result.support_score == 0.0


def test_conflicting_fact_lowers_score() -> None:
    cfg = ResearcherConfig()
    sources = [ResearchSource(id="s1", type="rag", title="doc", score=0.8)]
    ok = ConfidenceScorer.score([_supported_fact("s1")], sources, cfg)
    conflict = ConfidenceScorer.score([_supported_fact("s1", status="conflicting")], sources, cfg)
    assert conflict.support_score < ok.support_score


def test_inactive_source_lowers_score() -> None:
    cfg = ResearcherConfig()
    fact = _supported_fact("s1")
    active = ConfidenceScorer.score(
        [fact], [ResearchSource(id="s1", type="rag", title="СП", score=0.8, is_active=True)], cfg
    )
    inactive = ConfidenceScorer.score(
        [fact], [ResearchSource(id="s1", type="rag", title="СП", score=0.8, is_active=False)], cfg
    )
    assert inactive.support_score < active.support_score


def test_missing_jurisdiction_penalty_only_for_normative() -> None:
    cfg = ResearcherConfig()
    fact = _supported_fact("s1")
    norm = ConfidenceScorer.score(
        [fact],
        [ResearchSource(id="s1", type="rag", title="ГОСТ 1", score=0.8, jurisdiction=None)],
        cfg,
    )
    web = ConfidenceScorer.score(
        [fact],
        [ResearchSource(id="s1", type="web", title="blog", score=0.8, jurisdiction=None)],
        cfg,
    )
    assert norm.source_currency_score < web.source_currency_score


def test_multiple_independent_sources_increase_score() -> None:
    cfg = ResearcherConfig()
    one = ConfidenceScorer.score(
        [_supported_fact("s1")], [ResearchSource(id="s1", type="rag", title="doc", score=0.8)], cfg
    )
    multi = ConfidenceScorer.score(
        [_supported_fact("s1"), _supported_fact("s2")],
        [
            ResearchSource(id="s1", type="rag", title="doc1", score=0.8),
            ResearchSource(id="s2", type="rag", title="doc2", score=0.8),
        ],
        cfg,
    )
    assert multi.independent_sources > one.independent_sources


def test_llm_self_confidence_cannot_inflate_score() -> None:
    cfg = ResearcherConfig()
    fact = ResearchFact(text="x", source_ids=[], confidence=1.0)
    result = ConfidenceScorer.score([fact], [], cfg)
    assert result.llm_self_reported_confidence == 0.0
    assert result.support_score == 0.0
