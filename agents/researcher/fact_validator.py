from __future__ import annotations

import difflib
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
            valid_source_ids = [sid for sid in fact.source_ids if sid in by_id]
            if not valid_source_ids:
                diagnostics.append(
                    Diagnostic(
                        code="fact_invalid_source_ids",
                        message=f"Факт #{idx} отброшен: нет валидных source_ids",
                        severity="warn",
                        stage="fact_validation",
                    )
                )
                continue

            matched = False
            for source_id in valid_source_ids:
                snippet = by_id[source_id].snippet or ""
                if fuzz is not None:
                    similarity = fuzz.partial_ratio(fact.text, snippet) / 100.0
                else:
                    similarity = difflib.SequenceMatcher(None, fact.text, snippet).ratio()
                if similarity >= threshold:
                    matched = True
                    break

            if not matched:
                diagnostics.append(
                    Diagnostic(
                        code="fact_unsupported_quote",
                        message=f"Факт #{idx} отброшен: не подтверждается цитатой источника",
                        severity="warn",
                        stage="fact_validation",
                    )
                )
                continue

            validated.append(fact.model_copy(update={"source_ids": valid_source_ids}))

        return validated, diagnostics
