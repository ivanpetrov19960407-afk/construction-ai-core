from agents.researcher.config import ResearcherConfig
from agents.researcher.confidence import ConfidenceScorer
from schemas.research import ResearchFact, ResearchSource


def test_confidence_scorer_boundaries() -> None:
    cfg = ResearcherConfig(confidence_weight_fact=0.6, confidence_weight_source=0.4)
    facts = [ResearchFact(text="x", applicability="", confidence=1.0, source_ids=["rag-0"])]
    sources = [ResearchSource(id="rag-0", type="rag", title="doc", score=1.0)]
    result = ConfidenceScorer.score(facts, sources, cfg)
    assert result.overall == 1.0
