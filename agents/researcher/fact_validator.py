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

            has_supported = False
            has_unsupported = False
            has_conflict = False
            has_non_entailing = False
            updated_evidence: list[ResearchEvidence] = []
            validated_source_ids: list[str] = []

            for source_id in candidate_source_ids:
                source = by_id[source_id]
                source_evidence = [item for item in fact.evidence if item.source_id == source_id]
                if not source_evidence:
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

                source_has_valid = False
                for evidence in source_evidence:
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

                    match = FactValidator._find_quote(source, evidence.quote)
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
                    elif not FactValidator._is_entailing(fact.text, evidence.quote, source):
                        support_status = "quote_found_but_not_entailing"
                        has_non_entailing = True
                    source_has_valid = True

                    if support_status == "conflicting":
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
                    if support_status == "quote_found_but_not_entailing":
                        diagnostics.append(
                            Diagnostic(
                                code="fact_quote_not_entailing",
                                message=f"fact#{idx}: quote not entailing for source_id={source_id}",
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
                    if support_status == "supported":
                        has_supported = True
                if source_has_valid:
                    validated_source_ids.append(source_id)

            if not (has_supported or has_conflict or has_non_entailing):
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
            elif has_non_entailing and not has_supported:
                status = "quote_found_but_not_entailing"
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
        normalized_quote = FactValidator._normalize_text(quote)
        fields = {
            "snippet": source.snippet or "",
            "chunk_text": source.chunk_text or "",
            "full_text": source.full_text or "",
        }
        for name, text in fields.items():
            if not text:
                continue
            start = FactValidator._find_normalized_substring_start(text, normalized_quote)
            if start is not None:
                return (name, start, start + len(quote))
        return None

    @staticmethod
    def _find_normalized_substring_start(text: str, normalized_substring: str) -> int | None:
        if not normalized_substring:
            return None
        normalized_chars: list[str] = []
        index_map: list[int] = []
        for idx, ch in enumerate(text):
            lower = ch.lower()
            if ch.isspace():
                if normalized_chars and normalized_chars[-1] != " ":
                    normalized_chars.append(" ")
                    index_map.append(idx)
                continue
            normalized_chars.append(lower)
            index_map.append(idx)
        normalized_text = "".join(normalized_chars).strip()
        pos = normalized_text.find(normalized_substring)
        if pos < 0 or pos >= len(index_map):
            return None
        return index_map[pos]

    @staticmethod
    def _is_conflicting(fact_text: str, quote: str) -> bool:
        left = FactValidator._normalize_text(fact_text)
        right = FactValidator._normalize_text(quote)
        neg_words = ("not", "нет", "не ", "запрещ", "forbid", "нельзя")
        left_neg = any(w in left for w in neg_words)
        right_neg = any(w in right for w in neg_words)
        return left_neg != right_neg

    @staticmethod
    def _is_entailing(fact_text: str, quote: str, source: ResearchSource) -> bool:
        fact = FactValidator._normalize_text(fact_text)
        quote_norm = FactValidator._normalize_text(quote)
        obligation_terms = ("обязан", "требуется", "должен", "запрещ", "допускается", "необходимо")
        if any(term in fact for term in obligation_terms) and not any(
            term in quote_norm for term in obligation_terms
        ):
            return False
        if any(term in fact for term in ("гост", "сп", "фз", "снип")):
            if not any(term in quote_norm for term in ("гост", "сп", "фз", "снип")) and not (
                source.jurisdiction or source.authority
            ):
                return False
        if "редакц" in fact or "верси" in fact or "действ" in fact:
            if not (source.document_version or source.effective_from or source.effective_to):
                return False
        return True
