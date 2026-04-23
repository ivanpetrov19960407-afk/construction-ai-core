from agents.researcher.config import ResearcherConfig
from agents.researcher.fact_validator import FactValidator
from schemas.research import ResearchEvidence, ResearchFact, ResearchSource


def test_fact_validator_drops_missing_source() -> None:
    facts = [ResearchFact(text="Факт", applicability="", confidence=0.7, source_ids=["missing"])]
    sources = [ResearchSource(id="rag-0", type="rag", title="doc", snippet="Факт", score=0.9)]
    validated, diagnostics = FactValidator.validate(facts, sources, ResearcherConfig())
    assert validated == []
    assert diagnostics


def test_fact_validator_drops_unmatched_quote() -> None:
    facts = [
        ResearchFact(
            text="Бетон B30 требуется", applicability="", confidence=0.7, source_ids=["rag-0"]
        )
    ]
    sources = [
        ResearchSource(id="rag-0", type="rag", title="doc", snippet="Про арматуру", score=0.9)
    ]
    validated, diagnostics = FactValidator.validate(facts, sources, ResearcherConfig())
    assert validated == []
    assert any(d.code == "fact_unsupported_quote" for d in diagnostics)


def test_fact_validator_prunes_unsupported_source_ids_independently() -> None:
    facts = [
        ResearchFact(
            text="Бетон B30",
            applicability="",
            confidence=0.7,
            source_ids=["rag-0", "rag-1"],
        )
    ]
    sources = [
        ResearchSource(
            id="rag-0", type="rag", title="doc0", snippet="Бетон B30", score=0.9
        ),
        ResearchSource(
            id="rag-1", type="rag", title="doc1", snippet="Требуется арматура A500.", score=0.9
        ),
    ]
    validated, diagnostics = FactValidator.validate(facts, sources, ResearcherConfig())
    assert len(validated) == 1
    assert validated[0].source_ids == ["rag-0"]
    assert any(d.code == "fact_pruned_unsupported_sources" for d in diagnostics)


def test_fact_validator_accepts_exact_evidence_quote() -> None:
    facts = [
        ResearchFact(
            text="X",
            applicability="",
            confidence=0.7,
            source_ids=["rag-0"],
            evidence=[ResearchEvidence(source_id="rag-0", quote="Класс бетона B30")],
        )
    ]
    sources = [
        ResearchSource(
            id="rag-0",
            type="rag",
            title="doc",
            snippet="...Класс бетона B30 применяется...",
            score=0.8,
        )
    ]
    validated, diagnostics = FactValidator.validate(facts, sources, ResearcherConfig())
    assert len(validated) == 1
    assert diagnostics == []
