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
    validated, _ = FactValidator.validate(facts, sources)
    assert len(validated) == 1
    assert validated[0].support_status == "supported"
    assert validated[0].evidence[0].span_start is not None


def test_missing_quote_fails() -> None:
    facts = [
        ResearchFact(
            text="x",
            source_ids=["s1"],
            evidence=[ResearchEvidence(source_id="s1", quote="")],
        )
    ]
    sources = [ResearchSource(id="s1", type="rag", title="doc", snippet="text")]
    validated, _ = FactValidator.validate(facts, sources)
    assert validated == []


def test_fake_source_id_fails() -> None:
    facts = [
        ResearchFact(
            text="x",
            source_ids=["fake"],
            evidence=[ResearchEvidence(source_id="fake", quote="x")],
        )
    ]
    sources = [ResearchSource(id="s1", type="rag", title="doc", snippet="x")]
    validated, diags = FactValidator.validate(facts, sources)
    assert validated == []
    assert any(d.code == "fact_invalid_source_ids" for d in diags)


def test_fuzzy_only_match_fails() -> None:
    facts = [ResearchFact(text="Парафраз", source_ids=["s1"], evidence=[])]
    sources = [ResearchSource(id="s1", type="rag", title="doc", snippet="Похожий текст")]
    validated, _ = FactValidator.validate(facts, sources)
    assert validated == []


def test_paraphrase_without_quote_fails() -> None:
    facts = [
        ResearchFact(
            text="Бетон B30 обязателен",
            source_ids=["s1"],
            evidence=[ResearchEvidence(source_id="s1", quote="иное требование")],
        )
    ]
    sources = [ResearchSource(id="s1", type="rag", title="doc", snippet="Класс бетона B30")]
    validated, _ = FactValidator.validate(facts, sources)
    assert validated == []


def test_conflicting_evidence_is_returned_with_conflicting_status() -> None:
    facts = [
        ResearchFact(
            text="Бетон B30 не обязателен",
            source_ids=["s1"],
            evidence=[ResearchEvidence(source_id="s1", quote="Бетон B30 обязателен")],
        )
    ]
    sources = [ResearchSource(id="s1", type="rag", title="doc", snippet="Бетон B30 обязателен")]
    validated, _ = FactValidator.validate(facts, sources)
    assert len(validated) == 1
    assert validated[0].support_status == "conflicting"


def test_partial_support_status() -> None:
    facts = [
        ResearchFact(
            text="x",
            source_ids=["s1", "s2"],
            evidence=[ResearchEvidence(source_id="s1", quote="quote ok")],
        )
    ]
    sources = [
        ResearchSource(id="s1", type="rag", title="doc", snippet="quote ok"),
        ResearchSource(id="s2", type="rag", title="doc", snippet="other"),
    ]
    validated, _ = FactValidator.validate(facts, sources)
    assert validated[0].support_status == "partially_supported"


def test_quote_outside_snippet_inside_chunk_text_passes() -> None:
    facts = [
        ResearchFact(
            text="x",
            source_ids=["s1"],
            evidence=[ResearchEvidence(source_id="s1", quote="inside chunk")],
        )
    ]
    sources = [
        ResearchSource(
            id="s1",
            type="rag",
            title="doc",
            snippet="short",
            chunk_text="prefix inside chunk suffix",
        )
    ]
    validated, _ = FactValidator.validate(facts, sources)
    assert len(validated) == 1


def test_quote_outside_all_source_text_fails() -> None:
    facts = [
        ResearchFact(
            text="x",
            source_ids=["s1"],
            evidence=[ResearchEvidence(source_id="s1", quote="missing")],
        )
    ]
    sources = [
        ResearchSource(id="s1", type="rag", title="doc", snippet="short", chunk_text="another")
    ]
    validated, _ = FactValidator.validate(facts, sources)
    assert validated == []
