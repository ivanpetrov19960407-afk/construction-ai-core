"""Тесты для RAGEngine."""

from __future__ import annotations

import asyncio

from config.settings import settings
from core.rag_engine import RAGEngine


def test_ingest_text_and_search(tmp_path):
    settings.chroma_persist_dir = str(tmp_path / "chroma")

    rag = RAGEngine(collection_name="test_norms")
    added = rag.ingest_text(
        "СП 48.13330.2019 — общие положения",
        "СП_48",
        metadata={"tags": ["организация"], "scope": ["pto_engineer"]},
    )

    assert added > 0

    result = asyncio.run(
        rag.search(
            "требования к организации строительства",
            n_results=5,
            filter_scope="pto_engineer",
        )
    )

    assert result
    assert any(item["source"] == "СП_48" for item in result)


def test_search_filter_scope_and_stats(tmp_path):
    settings.chroma_persist_dir = str(tmp_path / "chroma_stats")
    rag = RAGEngine(collection_name="test_norms_stats")

    rag.ingest_text(
        "Требования по организации и производству работ.",
        "SP_48",
        metadata={"tags": ["организация"], "scope": ["pto_engineer", "foreman"]},
    )
    rag.ingest_text(
        "Требования для тендерного сопровождения.",
        "SP_118",
        metadata={"tags": ["тендер"], "scope": ["tender_specialist"]},
    )

    scoped = asyncio.run(rag.search("требования", n_results=10, filter_scope="tender_specialist"))
    assert scoped
    assert all("tender_specialist" in item["scope"] for item in scoped)

    stats = rag.get_stats()
    assert stats["total_chunks"] >= 2
    assert set(stats["sources"]) >= {"SP_48", "SP_118"}
    assert isinstance(stats["last_updated"], str)
    assert stats["last_updated"]
