from __future__ import annotations

import re

from agents.researcher.config import ResearcherConfig
from schemas.research import Diagnostic, ResearchEvidence, ResearchFact, ResearchSource


class FactValidator:
    """Strict evidence validator: exact quote match in source text only."""

    def __init__(self, min_similarity: float) -> None:
        self._min_similarity = min_similarity

    def validate_facts(
        self,
        facts: list[ResearchFact],
        sources: list[ResearchSource],
    ) -> tuple[list[ResearchFact], list[Diagnostic]]:
        return self._validate_impl(facts, sources, self._min_similarity)

    @staticmethod
    def validate(
        facts: list[ResearchFact],
        sources: list[ResearchSource],
        config: ResearcherConfig,
    ) -> tuple[list[ResearchFact], list[Diagnostic]]:
        return FactValidator._validate_impl(facts, sources, config.fact_citation_min_similarity)

    @staticmethod
    def _validate_impl(
        facts: list[ResearchFact],
        sources: list[ResearchSource],
        threshold: float,
    ) -> tuple[list[ResearchFact], list[Diagnostic]]:
        _ = threshold
        by_id = {source.id: source for source in sources}
        validated: list[ResearchFact] = []
        diagnostics: list[Diagnostic] = []

        for idx, fact in enumerate(facts, start=1):
            candidate_source_ids = [sid for sid in fact.source_ids if sid in by_id]
            rejected_source_ids = [sid for sid in fact.source_ids if sid not in by_id]
            if rejected_source_ids:
                diagnostics.append(
                    Diagnostic(
                        code="fact_invalid_source_ids",
                        message=f"fact#{idx}: invalid source_ids={rejected_source_ids}",
                        severity="warn",
                        component="fact_validator",
                        stage="validate",
                    )
                )
            if not candidate_source_ids:
                continue

            evidence_map = {item.source_id: item for item in fact.evidence if item.source_id}
            has_supported = False
            has_unsupported = False
            has_conflict = False
            updated_evidence: list[ResearchEvidence] = []
            validated_source_ids: list[str] = []

            for source_id in candidate_source_ids:
                source = by_id[source_id]
                evidence = evidence_map.get(source_id)
                if evidence is None:
                    has_unsupported = True
                    diagnostics.append(
                        Diagnostic(
                            code="fact_missing_evidence",
                            message=f"fact#{idx}: missing evidence for source_id={source_id}",
                            severity="warn",
                            component="fact_validator",
                            stage="validate",
                            source_id=source_id,
                        )
                    )
                    continue

                quote = FactValidator._normalize_text(evidence.quote)
                if not quote:
                    has_unsupported = True
                    updated_evidence.append(
                        evidence.model_copy(update={"support_status": "unsupported"})
                    )
                    diagnostics.append(
                        Diagnostic(
                            code="fact_missing_quote",
                            message=f"fact#{idx}: empty quote for source_id={source_id}",
                            severity="warn",
                            component="fact_validator",
                            stage="validate",
                            source_id=source_id,
                        )
                    )
                    continue

                match = FactValidator._find_quote(source, quote)
                if match is None:
                    has_unsupported = True
                    updated_evidence.append(
                        evidence.model_copy(update={"support_status": "unsupported"})
                    )
                    diagnostics.append(
                        Diagnostic(
                            code="fact_quote_not_found",
                            message=f"fact#{idx}: quote not found for source_id={source_id}",
                            severity="warn",
                            component="fact_validator",
                            stage="validate",
                            source_id=source_id,
                        )
                    )
                    continue

                support_status = "supported"
                if FactValidator._is_conflicting(fact.text, evidence.quote):
                    support_status = "conflicting"
                    has_conflict = True
                    diagnostics.append(
                        Diagnostic(
                            code="fact_conflicting_evidence",
                            message=f"fact#{idx}: conflicting evidence for source_id={source_id}",
                            severity="warn",
                            component="fact_validator",
                            stage="validate",
                            source_id=source_id,
                        )
                    )

                if match[0] == "snippet" and not (source.chunk_text or source.full_text):
                    diagnostics.append(
                        Diagnostic(
                            code="snippet_only_evidence",
                            message=f"fact#{idx}: evidence based on snippet only for {source_id}",
                            severity="info",
                            component="fact_validator",
                            stage="validate",
                            source_id=source_id,
                        )
                    )

                updated_evidence.append(
                    evidence.model_copy(
                        update={
                            "support_status": support_status,
                            "span_start": match[1],
                            "span_end": match[2],
                        }
                    )
                )
                has_supported = True
                validated_source_ids.append(source_id)

            if not has_supported:
                diagnostics.append(
                    Diagnostic(
                        code="fact_unsupported",
                        message=f"fact#{idx}: unsupported by exact quote evidence",
                        severity="warn",
                        component="fact_validator",
                        stage="validate",
                    )
                )
                continue

            status = "supported"
            if has_conflict:
                status = "conflicting"
            elif has_supported and has_unsupported:
                status = "partially_supported"
                diagnostics.append(
                    Diagnostic(
                        code="fact_partially_supported",
                        message=f"fact#{idx}: partially supported",
                        severity="info",
                        component="fact_validator",
                        stage="validate",
                    )
                )

            validated.append(
                fact.model_copy(
                    update={
                        "source_ids": validated_source_ids,
                        "support_status": status,
                        "evidence": updated_evidence,
                    }
                )
            )

        return validated, diagnostics

    @staticmethod
    def _normalize_text(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip().lower()

    @staticmethod
    def _find_quote(source: ResearchSource, quote: str) -> tuple[str, int, int] | None:
        fields = {
            "snippet": source.snippet or "",
            "chunk_text": source.chunk_text or "",
            "full_text": source.full_text or "",
        }
        for name, text in fields.items():
            normalized = FactValidator._normalize_text(text)
            if not normalized:
                continue
            start = normalized.find(quote)
            if start >= 0:
                return (name, start, start + len(quote))
        return None

    @staticmethod
    def _is_conflicting(fact_text: str, quote: str) -> bool:
        left = FactValidator._normalize_text(fact_text)
        right = FactValidator._normalize_text(quote)
        neg_words = ("not", "нет", "не ", "запрещ", "forbid", "нельзя")
        left_neg = any(w in left for w in neg_words)
        right_neg = any(w in right for w in neg_words)
        return left_neg != right_neg
