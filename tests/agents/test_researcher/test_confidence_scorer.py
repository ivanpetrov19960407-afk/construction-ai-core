from agents.researcher.confidence import ConfidenceScorer
from agents.researcher.config import ResearcherConfig
from schemas.research import ResearchFact, ResearchSource


def test_confidence_scorer_zero_without_facts() -> None:
    cfg = ResearcherConfig()
    sources = [ResearchSource(id="rag-0", type="rag", title="doc", score=1.0)]
    result = ConfidenceScorer.score([], sources, cfg)
    assert result.overall == 0.0


def test_confidence_scorer_positive_with_validated_facts_and_sources() -> None:
    cfg = ResearcherConfig()
    facts = [ResearchFact(text="x", applicability="", confidence=0.9, source_ids=["rag-0"])]
    sources = [ResearchSource(id="rag-0", type="rag", title="doc", score=0.9)]
    result = ConfidenceScorer.score(facts, sources, cfg)
    assert result.overall > 0


def test_llm_self_confidence_alone_not_high_without_source_support() -> None:
    cfg = ResearcherConfig()
    facts = [ResearchFact(text="x", applicability="", confidence=1.0, source_ids=[])]
    result = ConfidenceScorer.score(facts, [], cfg)
    assert result.overall < 0.2
