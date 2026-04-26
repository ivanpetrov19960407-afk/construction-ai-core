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
    source_currency_score: float = Field(ge=0.0, le=1.0)
    metadata_quality_score: float = Field(ge=0.0, le=1.0)
    conflict_penalty: float = Field(ge=0.0, le=1.0)
    support_score: float = Field(ge=0.0, le=1.0)
    llm_self_reported_confidence: float = Field(ge=0.0, le=1.0)
    weights: dict[str, float]
    explanation: str


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
                source_currency_score=0.0,
                metadata_quality_score=0.0,
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
        independent_documents: set[tuple[str, str]] = set()
        inactive_hits = 0
        missing_jurisdiction_normative_hits = 0
        conflict_hits = 0
        quote_not_entailing_hits = 0
        snippet_only_hits = 0

        for fact in facts:
            if fact.support_status == "conflicting":
                conflict_hits += 1
            evidence_supported = 0
            for ev in fact.evidence:
                if ev.source_id in source_by_id and ev.support_status in {
                    "supported",
                }:
                    evidence_supported += 1
                if ev.support_status == "quote_found_but_not_entailing":
                    quote_not_entailing_hits += 1
                if ev.source_id in source_by_id:
                    src = source_by_id[ev.source_id]
                    if ev.support_status in {"supported", "partially_supported"} and not (
                        src.chunk_text or src.full_text
                    ):
                        snippet_only_hits += 1
            if evidence_supported > 0:
                facts_with_supported_evidence += 1

            for sid in fact.source_ids:
                source_item = source_by_id.get(sid)
                if source_item is None:
                    continue
                unique_sources.add(sid)
                cited_scores.append(
                    source_item.quality_score
                    if source_item.quality_score is not None
                    else source_item.score
                )
                doc_key = (
                    source_item.document_id or source_item.document or source_item.title,
                    source_item.authority or "",
                )
                independent_documents.add(doc_key)
                if source_item.is_active is False:
                    inactive_hits += 1
                if is_normative_source(source_item) and not source_item.jurisdiction:
                    missing_jurisdiction_normative_hits += 1

        evidence_coverage = facts_with_supported_evidence / max(len(facts), 1)
        if quote_not_entailing_hits:
            evidence_coverage = max(0.0, evidence_coverage - 0.2)
        if snippet_only_hits:
            evidence_coverage = max(0.0, evidence_coverage - 0.1)
        source_quality = sum(cited_scores) / len(cited_scores) if cited_scores else 0.0
        independent_sources = 1 - math.exp(-len(independent_documents))

        source_currency_score = 0.0
        metadata_quality_score = 1.0 if cited_scores else 0.0
        if cited_scores:
            penalties = (inactive_hits * 0.35) + (missing_jurisdiction_normative_hits * 0.12)
            source_currency_score = max(0.0, 1.0 - penalties / max(len(cited_scores), 1))
            metadata_quality_score = max(
                0.0, 1.0 - (missing_jurisdiction_normative_hits / max(len(cited_scores), 1))
            )

        conflict_penalty = min(1.0, conflict_hits / max(len(facts), 1))

        if facts_with_supported_evidence == 0:
            return ConfidenceBreakdown(
                overall=0.0,
                evidence_coverage=0.0,
                source_quality=round(source_quality, 2),
                independent_sources=round(independent_sources, 2),
                source_currency_score=round(source_currency_score, 2),
                metadata_quality_score=round(metadata_quality_score, 2),
                conflict_penalty=round(min(1.0, conflict_hits / max(len(facts), 1)), 2),
                support_score=0.0,
                llm_self_reported_confidence=0.0,
                weights=ConfidenceScorer._weights(config),
                explanation=(
                    "support_score indicates evidence support quality, not probability of truth."
                ),
            )

        weights = ConfidenceScorer._weights(config)
        support_score = (
            evidence_coverage * weights["evidence_coverage"]
            + source_quality * weights["source_quality"]
            + independent_sources * weights["independent_sources"]
            + source_currency_score * weights["source_currency_score"]
            + metadata_quality_score * weights["metadata_quality_score"]
            - conflict_penalty * weights["conflict_penalty"]
        )
        if conflict_hits > 0:
            support_score = min(support_score, 0.35)
        support_score = max(0.0, min(1.0, support_score))
        return ConfidenceBreakdown(
            overall=round(support_score, 2),
            evidence_coverage=round(evidence_coverage, 2),
            source_quality=round(source_quality, 2),
            independent_sources=round(independent_sources, 2),
            source_currency_score=round(source_currency_score, 2),
            metadata_quality_score=round(metadata_quality_score, 2),
            conflict_penalty=round(conflict_penalty, 2),
            support_score=round(support_score, 2),
            llm_self_reported_confidence=0.0,
            weights=weights,
            explanation=(
                "support_score indicates evidence support quality, not probability of truth."
            ),
        )

    @staticmethod
    def _weights(config: ResearcherConfig) -> dict[str, float]:
        return {
            "evidence_coverage": config.support_weight_evidence_coverage,
            "source_quality": config.support_weight_source_quality,
            "independent_sources": config.support_weight_independent_sources,
            "source_currency_score": config.support_weight_recency,
            "metadata_quality_score": 0.1,
            "conflict_penalty": config.support_weight_conflict_penalty,
        }
