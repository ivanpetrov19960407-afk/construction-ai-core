from __future__ import annotations

from pydantic import BaseModel, Field

from agents.researcher.config import ResearcherConfig
from schemas.research import ResearchFact, ResearchSource


class ConfidenceBreakdown(BaseModel):
    overall: float = Field(ge=0.0, le=1.0)
    from_facts: float = Field(ge=0.0, le=1.0)
    from_sources: float = Field(ge=0.0, le=1.0)
    weights: dict[str, float]
    explanation: str


class ConfidenceScorer:
    @staticmethod
    def score(
        facts: list[ResearchFact],
        sources: list[ResearchSource],
        config: ResearcherConfig,
    ) -> ConfidenceBreakdown:
        fact_avg = sum(f.confidence for f in facts) / len(facts) if facts else 0.0
        src_avg = sum(s.score for s in sources) / len(sources) if sources else 0.0
        score = (fact_avg * config.confidence_weight_fact) + (
            src_avg * config.confidence_weight_source
        )
        return ConfidenceBreakdown(
            overall=round(min(1.0, max(0.0, score)), 2),
            from_facts=round(fact_avg, 2),
            from_sources=round(src_avg, 2),
            weights={
                "fact": config.confidence_weight_fact,
                "source": config.confidence_weight_source,
            },
            explanation="Weighted blend of fact confidence and source quality.",
        )
