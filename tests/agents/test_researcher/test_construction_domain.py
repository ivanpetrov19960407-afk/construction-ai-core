from agents.researcher.domain import choose_primary_sources, detect_version_conflict
from schemas.research import ResearchSource


def test_active_norm_beats_inactive_norm() -> None:
    sources = [
        ResearchSource(
            id="a", type="rag", title="СП 63", is_active=True, document_version="2025", score=0.6
        ),
        ResearchSource(
            id="b", type="rag", title="СП 63", is_active=False, document_version="2012", score=0.9
        ),
    ]
    ranked = choose_primary_sources("актуальная норма", sources)
    assert ranked[0].id == "a"


def test_conflicting_versions_detected() -> None:
    sources = [
        ResearchSource(
            id="a", type="rag", title="СП 63", document="СП 63", document_version="2012", score=0.9
        ),
        ResearchSource(
            id="b", type="rag", title="СП 63", document="СП 63", document_version="2025", score=0.8
        ),
    ]
    diags = detect_version_conflict(sources)
    assert any(d.code == "source_version_conflict" for d in diags)


def test_project_doc_does_not_override_norm_by_default() -> None:
    sources = [
        ResearchSource(id="n", type="rag", title="ГОСТ 1", score=0.6),
        ResearchSource(id="p", type="rag", title="Проектная документация", score=0.95),
    ]
    ranked = choose_primary_sources("по ГОСТ бетон", sources)
    assert ranked[0].id == "n"


def test_project_specific_query_may_prioritize_project_document() -> None:
    sources = [
        ResearchSource(id="n", type="rag", title="ГОСТ 1", score=0.6),
        ResearchSource(id="p", type="rag", title="Проектная документация", score=0.95),
    ]
    ranked = choose_primary_sources("для проекта по проекту", sources)
    assert ranked[0].id == "p"
