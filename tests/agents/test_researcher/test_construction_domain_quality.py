from agents.researcher.confidence import ConfidenceScorer
from agents.researcher.config import ResearcherConfig
from schemas.research import ResearchEvidence, ResearchFact, ResearchSource


def _fact(ids: list[str]) -> ResearchFact:
    return ResearchFact(
        text="Минимальный класс бетона B30",
        source_ids=ids,
        support_status="supported",
        evidence=[
            ResearchEvidence(source_id=ids[0], quote="класс бетона B30", support_status="supported")
        ],
    )


def test_active_norm_beats_inactive_norm() -> None:
    cfg = ResearcherConfig()
    facts = [_fact(["active"])]
    active = [
        ResearchSource(
            id="active",
            type="rag",
            title="СП 63",
            score=0.8,
            jurisdiction="RU",
            authority="Минстрой",
            is_active=True,
            document_version="2025",
        )
    ]
    inactive = [
        ResearchSource(
            id="active",
            type="rag",
            title="СП 63 old",
            score=0.8,
            jurisdiction="RU",
            authority="Минстрой",
            is_active=False,
            document_version="2012",
        )
    ]
    assert (
        ConfidenceScorer.score(facts, active, cfg).overall
        > ConfidenceScorer.score(facts, inactive, cfg).overall
    )


def test_outdated_source_flagged_by_recency() -> None:
    cfg = ResearcherConfig()
    facts = [_fact(["s1"])]
    src = [ResearchSource(id="s1", type="rag", title="old", score=0.9, is_active=False)]
    assert ConfidenceScorer.score(facts, src, cfg).recency_score < 1.0


def test_conflicting_versions_detected() -> None:
    cfg = ResearcherConfig()
    facts = [ResearchFact(text="x", source_ids=["s1"], support_status="conflicting")]
    src = [ResearchSource(id="s1", type="rag", title="ГОСТ doc", score=0.8, jurisdiction="RU")]
    assert ConfidenceScorer.score(facts, src, cfg).conflict_penalty > 0


def test_missing_jurisdiction_reduces_score() -> None:
    cfg = ResearcherConfig()
    facts = [_fact(["s1"])]
    with_j = [ResearchSource(id="s1", type="rag", title="ГОСТ doc", score=0.8, jurisdiction="RU")]
    no_j = [ResearchSource(id="s1", type="rag", title="ГОСТ doc", score=0.8, jurisdiction=None)]
    assert (
        ConfidenceScorer.score(facts, with_j, cfg).overall
        > ConfidenceScorer.score(facts, no_j, cfg).overall
    )
