from __future__ import annotations

from pydantic import BaseModel, Field

from agents.researcher.config import ResearcherConfig
from schemas.research import ResearchFact, ResearchSource


class ConfidenceBreakdown(BaseModel):
    overall: float = Field(ge=0.0, le=1.0)
    retrieval_support: float = Field(ge=0.0, le=1.0)
    citation_coverage: float = Field(ge=0.0, le=1.0)
    source_quality: float = Field(ge=0.0, le=1.0)
    llm_self_reported_confidence: float = Field(ge=0.0, le=1.0)
    weights: dict[str, float]
    explanation: str


class ConfidenceScorer:
    def __init__(self, config: ResearcherConfig) -> None:
        self._config = config

    def compute(
        self,
        facts: list[ResearchFact],
        sources: list[ResearchSource],
    ) -> ConfidenceBreakdown:
        return self.score(facts, sources, self._config)

    @staticmethod
    def score(
        facts: list[ResearchFact],
        sources: list[ResearchSource],
        config: ResearcherConfig,
    ) -> ConfidenceBreakdown:
        if not facts:
            return ConfidenceBreakdown(
                overall=0.0,
                retrieval_support=0.0,
                citation_coverage=0.0,
                source_quality=0.0,
                llm_self_reported_confidence=0.0,
                weights={
                    "retrieval_support": 0.35,
                    "citation_coverage": 0.35,
                    "source_quality": 0.25,
                    "llm_self_reported_confidence": 0.05,
                },
                explanation="No validated facts -> confidence is zero.",
            )

        source_by_id = {s.id: s for s in sources}
        cited_scores: list[float] = []
        cited_count = 0
        for fact in facts:
            for sid in fact.source_ids:
                src = source_by_id.get(sid)
                if src is None:
                    continue
                cited_count += 1
                cited_scores.append(src.score)

        retrieval_support = sum(cited_scores) / len(cited_scores) if cited_scores else 0.0
        citation_coverage = cited_count / max(len(facts), 1)
        citation_coverage = min(1.0, citation_coverage)
        source_quality = sum(s.score for s in sources) / len(sources) if sources else 0.0
        llm_self_reported_confidence = sum(f.confidence for f in facts) / len(facts)
        score = (
            retrieval_support * 0.35
            + citation_coverage * 0.35
            + source_quality * 0.25
            + llm_self_reported_confidence * 0.05
        )
        return ConfidenceBreakdown(
            overall=round(min(1.0, max(0.0, score)), 2),
            retrieval_support=round(retrieval_support, 2),
            citation_coverage=round(citation_coverage, 2),
            source_quality=round(source_quality, 2),
            llm_self_reported_confidence=round(llm_self_reported_confidence, 2),
            weights={
                "retrieval_support": 0.35,
                "citation_coverage": 0.35,
                "source_quality": 0.25,
                "llm_self_reported_confidence": 0.05,
            },
            explanation=(
                "Confidence reflects validated citation support; LLM self-score has low weight."
            ),
        )
