from __future__ import annotations

import math

from pydantic import BaseModel, Field

from agents.researcher.config import ResearcherConfig
from agents.researcher.domain import is_normative_source
from schemas.research import ResearchFact, ResearchSource


class ConfidenceBreakdown(BaseModel):
    overall: float = Field(ge=0.0, le=1.0)
    evidence_coverage: float = Field(ge=0.0, le=1.0)
    source_quality: float = Field(ge=0.0, le=1.0)
    independent_sources: float = Field(ge=0.0, le=1.0)
    recency_score: float = Field(ge=0.0, le=1.0)
    conflict_penalty: float = Field(ge=0.0, le=1.0)
    support_score: float = Field(ge=0.0, le=1.0)
    llm_self_reported_confidence: float = Field(ge=0.0, le=1.0)
    weights: dict[str, float]
    explanation: str

    @property
    def citation_coverage(self) -> float:
        """Backward-compatible alias."""
        return self.evidence_coverage


class ConfidenceScorer:
    def __init__(self, config: ResearcherConfig) -> None:
        self._config = config

    def compute(
        self, facts: list[ResearchFact], sources: list[ResearchSource]
    ) -> ConfidenceBreakdown:
        return self.score(facts, sources, self._config)

    @staticmethod
    def score(
        facts: list[ResearchFact], sources: list[ResearchSource], config: ResearcherConfig
    ) -> ConfidenceBreakdown:
        if not facts:
            return ConfidenceBreakdown(
                overall=0.0,
                evidence_coverage=0.0,
                source_quality=0.0,
                independent_sources=0.0,
                recency_score=0.0,
                conflict_penalty=0.0,
                support_score=0.0,
                llm_self_reported_confidence=0.0,
                weights=ConfidenceScorer._weights(config),
                explanation="No validated facts -> score is zero.",
            )

        source_by_id = {s.id: s for s in sources}
        facts_with_supported_evidence = 0
        cited_scores: list[float] = []
        unique_sources: set[str] = set()
        inactive_hits = 0
        missing_jurisdiction_normative_hits = 0
        conflict_hits = 0

        for fact in facts:
            if fact.support_status == "conflicting":
                conflict_hits += 1
            evidence_supported = 0
            for ev in fact.evidence:
                if ev.source_id in source_by_id and ev.support_status in {"supported", "conflicting"}:
                    evidence_supported += 1
            if evidence_supported > 0:
                facts_with_supported_evidence += 1

            for sid in fact.source_ids:
                src = source_by_id.get(sid)
                if src is None:
                    continue
                unique_sources.add(sid)
                cited_scores.append(src.quality_score if src.quality_score is not None else src.score)
                if src.is_active is False:
                    inactive_hits += 1
                if is_normative_source(src) and not src.jurisdiction:
                    missing_jurisdiction_normative_hits += 1

        evidence_coverage = facts_with_supported_evidence / max(len(facts), 1)
        source_quality = sum(cited_scores) / len(cited_scores) if cited_scores else 0.0
        independent_sources = 1 - math.exp(-len(unique_sources))

        recency_score = 0.0
        if cited_scores:
            penalties = (inactive_hits * 0.2) + (missing_jurisdiction_normative_hits * 0.1)
            recency_score = max(0.0, 1.0 - penalties / max(len(cited_scores), 1))

        conflict_penalty = min(1.0, conflict_hits / max(len(facts), 1))

        if facts_with_supported_evidence == 0:
            return ConfidenceBreakdown(
                overall=0.0,
                evidence_coverage=0.0,
                source_quality=round(source_quality, 2),
                independent_sources=round(independent_sources, 2),
                recency_score=round(recency_score, 2),
                conflict_penalty=round(min(1.0, conflict_hits / max(len(facts), 1)), 2),
                support_score=0.0,
                llm_self_reported_confidence=0.0,
                weights=ConfidenceScorer._weights(config),
                explanation="support_score indicates evidence support quality, not probability of truth.",
            )

        weights = ConfidenceScorer._weights(config)
        support_score = (
            evidence_coverage * weights["evidence_coverage"]
            + source_quality * weights["source_quality"]
            + independent_sources * weights["independent_sources"]
            + recency_score * weights["recency_score"]
            - conflict_penalty * weights["conflict_penalty"]
        )
        support_score = max(0.0, min(1.0, support_score))
        return ConfidenceBreakdown(
            overall=round(support_score, 2),
            evidence_coverage=round(evidence_coverage, 2),
            source_quality=round(source_quality, 2),
            independent_sources=round(independent_sources, 2),
            recency_score=round(recency_score, 2),
            conflict_penalty=round(conflict_penalty, 2),
            support_score=round(support_score, 2),
            llm_self_reported_confidence=0.0,
            weights=weights,
            explanation="support_score indicates evidence support quality, not probability of truth.",
        )

    @staticmethod
    def _weights(config: ResearcherConfig) -> dict[str, float]:
        return {
            "evidence_coverage": config.support_weight_evidence_coverage,
            "source_quality": config.support_weight_source_quality,
            "independent_sources": config.support_weight_independent_sources,
            "recency_score": config.support_weight_recency,
            "conflict_penalty": config.support_weight_conflict_penalty,
        }
