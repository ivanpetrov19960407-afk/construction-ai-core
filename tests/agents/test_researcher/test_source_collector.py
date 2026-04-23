import asyncio

from agents.researcher.config import ResearcherConfig
from agents.researcher.source_collector import SourceCollector


class _Rag:
    async def search(self, query: str, n_results: int, filter_scope: str | None = None):
        _ = (query, n_results, filter_scope)
        return [
            {"source": "СП", "page": 1, "text": "Бетон B30", "score": 0.9},
            {"source": "СП", "page": 1, "text": "Бетон B30", "score": 0.8},
        ]


class _Web:
    async def run(self, query: str, max_results: int):
        _ = (query, max_results)
        return [{"title": "x", "url": "https://example.com", "snippet": "s", "score": 0.5}]


def test_source_collector_dedup() -> None:
    collector = SourceCollector(_Rag(), _Web(), None, ResearcherConfig(top_k_sources=5))  # type: ignore[arg-type]
    sources, _ = asyncio.run(
        collector.collect("бетон", topic_scope=None, access_scope=None, context="")
    )
    rag_sources = [s for s in sources if s.type == "rag"]
    assert len(rag_sources) == 1
