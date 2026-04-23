from __future__ import annotations

import difflib
import re
from types import ModuleType

try:
    from rapidfuzz import fuzz
except Exception:  # pragma: no cover
    fuzz: ModuleType | None = None

from agents.researcher.config import ResearcherConfig
from schemas.research import Diagnostic, ResearchFact, ResearchSource


class FactValidator:
    """Validates citations and filters dangling facts."""

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
        by_id = {source.id: source for source in sources}
        validated: list[ResearchFact] = []
        diagnostics: list[Diagnostic] = []

        for idx, fact in enumerate(facts, start=1):
            invalid_source_ids = [sid for sid in fact.source_ids if sid not in by_id]
            if invalid_source_ids:
                diagnostics.append(
                    Diagnostic(
                        code="fact_invalid_source_ids",
                        message=f"Факт #{idx}: несуществующие source_ids={invalid_source_ids}",
                        severity="warn",
                        stage="fact_validation",
                    )
                )

            candidate_source_ids = [sid for sid in fact.source_ids if sid in by_id]
            if not candidate_source_ids:
                diagnostics.append(
                    Diagnostic(
                        code="fact_invalid_source_ids",
                        message=f"Факт #{idx} отброшен: нет валидных source_ids",
                        severity="warn",
                        stage="fact_validation",
                    )
                )
                continue

            supported_source_ids: list[str] = []
            used_similarity_fallback = False
            evidence_by_source = {item.source_id: item for item in fact.evidence if item.source_id}

            for source_id in candidate_source_ids:
                snippet = by_id[source_id].snippet or ""
                normalized_snippet = FactValidator._normalize_text(snippet)
                evidence = evidence_by_source.get(source_id)
                if evidence is not None:
                    quote = FactValidator._normalize_text(evidence.quote)
                    if quote and quote in normalized_snippet:
                        supported_source_ids.append(source_id)
                    continue

                if fuzz is not None:
                    similarity = fuzz.partial_ratio(fact.text, snippet) / 100.0
                else:
                    similarity = difflib.SequenceMatcher(None, fact.text, snippet).ratio()
                if similarity >= threshold:
                    supported_source_ids.append(source_id)
                    used_similarity_fallback = True

            if not supported_source_ids:
                diagnostics.append(
                    Diagnostic(
                        code="fact_unsupported_quote",
                        message=f"Факт #{idx} отброшен: не подтверждается цитатой источника",
                        severity="warn",
                        stage="fact_validation",
                    )
                )
                continue

            if len(supported_source_ids) < len(candidate_source_ids):
                pruned = sorted(set(candidate_source_ids) - set(supported_source_ids))
                diagnostics.append(
                    Diagnostic(
                        code="fact_pruned_unsupported_sources",
                        message=f"Факт #{idx}: удалены неподтверждённые source_ids={pruned}",
                        severity="warn",
                        stage="fact_validation",
                    )
                )

            if used_similarity_fallback:
                diagnostics.append(
                    Diagnostic(
                        code="fact_validated_by_similarity_fallback",
                        message=f"Факт #{idx}: подтвержден similarity fallback",
                        severity="info",
                        stage="fact_validation",
                    )
                )

            validated.append(fact.model_copy(update={"source_ids": supported_source_ids}))

        return validated, diagnostics

    @staticmethod
    def _normalize_text(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip().lower()
