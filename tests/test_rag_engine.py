"""Тесты для RAGEngine."""

from __future__ import annotations

import asyncio

from config.settings import settings
from core.rag_engine import RAGEngine


def test_ingest_text_and_search(tmp_path):
    settings.chroma_persist_dir = str(tmp_path / "chroma")

    rag = RAGEngine(collection_name="test_norms")
    added = rag.ingest_text("СП 48.13330.2019 — общие положения", "СП_48")

    assert added > 0

    result = asyncio.run(rag.search("требования к организации строительства", n_results=5))

    assert result
    assert any(item["source"] == "СП_48" for item in result)
