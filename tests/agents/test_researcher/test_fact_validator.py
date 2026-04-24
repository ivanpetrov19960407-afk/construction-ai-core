from agents.researcher.config import ResearcherConfig
from agents.researcher.fact_validator import FactValidator
from schemas.research import ResearchEvidence, ResearchFact, ResearchSource


def test_exact_quote_passes() -> None:
    facts = [
        ResearchFact(
            text="Бетон B30 обязателен",
            source_ids=["s1"],
            evidence=[ResearchEvidence(source_id="s1", quote="Класс бетона B30")],
        )
    ]
    sources = [ResearchSource(id="s1", type="rag", title="doc", snippet="...Класс бетона B30...")]
    validated, _ = FactValidator.validate(facts, sources, ResearcherConfig())
    assert len(validated) == 1
    assert validated[0].support_status == "supported"


def test_missing_quote_fails() -> None:
    facts = [
        ResearchFact(
            text="x", source_ids=["s1"], evidence=[ResearchEvidence(source_id="s1", quote="")]
        )
    ]
    sources = [ResearchSource(id="s1", type="rag", title="doc", snippet="text")]
    validated, _ = FactValidator.validate(facts, sources, ResearcherConfig())
    assert validated == []


def test_fake_source_id_fails() -> None:
    facts = [
        ResearchFact(
            text="x", source_ids=["fake"], evidence=[ResearchEvidence(source_id="fake", quote="x")]
        )
    ]
    sources = [ResearchSource(id="s1", type="rag", title="doc", snippet="x")]
    validated, _ = FactValidator.validate(facts, sources, ResearcherConfig())
    assert validated == []


def test_fuzzy_only_does_not_pass() -> None:
    facts = [ResearchFact(text="Парафраз", source_ids=["s1"], evidence=[])]
    sources = [ResearchSource(id="s1", type="rag", title="doc", snippet="Похожий текст")]
    validated, _ = FactValidator.validate(facts, sources, ResearcherConfig())
    assert validated == []


def test_paraphrase_without_quote_does_not_pass() -> None:
    facts = [
        ResearchFact(
            text="Бетон B30 обязателен",
            source_ids=["s1"],
            evidence=[ResearchEvidence(source_id="s1", quote="другой текст")],
        )
    ]
    sources = [ResearchSource(id="s1", type="rag", title="doc", snippet="Класс бетона B30")]
    validated, _ = FactValidator.validate(facts, sources, ResearcherConfig())
    assert validated == []


def test_conflicting_evidence_marked() -> None:
    facts = [
        ResearchFact(
            text="Бетон B30 не обязателен",
            source_ids=["s1"],
            evidence=[ResearchEvidence(source_id="s1", quote="Бетон B30 обязателен")],
        )
    ]
    sources = [ResearchSource(id="s1", type="rag", title="doc", snippet="Бетон B30 обязателен")]
    validated, _ = FactValidator.validate(facts, sources, ResearcherConfig())
    assert validated == []
