import asyncio

import pytest

from agents.researcher.config import ResearcherConfig
from agents.researcher.errors import ResearchLLMError, ResearchValidationError
from agents.researcher.llm_client import StructuredLLMClient


class _Resp:
    def __init__(self, text: str):
        self.text = text


class _Router:
    def __init__(self, responses: list[str], *, delay: float = 0.0, fail: bool = False):
        self._responses = responses
        self.delay = delay
        self.calls = 0
        self.fail = fail

    async def query(self, prompt: str, system_prompt: str):
        _ = (prompt, system_prompt)
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise RuntimeError("router down")
        if self.calls > len(self._responses):
            return _Resp(self._responses[-1])
        return _Resp(self._responses[self.calls - 1])


def test_timeout_diagnostic() -> None:
    client = StructuredLLMClient(
        _Router(['{"facts": [], "gaps": []}'], delay=0.02),  # type: ignore[arg-type]
        ResearcherConfig(llm_timeout_seconds=0.001, retry_attempts=1),
    )
    with pytest.raises(TimeoutError):
        asyncio.run(client.generate("p", system_prompt="s"))


def test_invalid_json_diagnostic() -> None:
    client = StructuredLLMClient(
        _Router(["not json", "still not json"]),  # type: ignore[arg-type]
        ResearcherConfig(llm_reask_limit=1),
    )
    with pytest.raises(ResearchLLMError):
        asyncio.run(client.generate("p", system_prompt="s"))


def test_schema_validation_diagnostic() -> None:
    client = StructuredLLMClient(_Router(['{"facts": "oops", "gaps": []}']), ResearcherConfig())  # type: ignore[arg-type]
    with pytest.raises(ResearchValidationError):
        asyncio.run(client.query("p", "s"))


def test_access_error_diagnostic() -> None:
    from agents.researcher.errors import ResearchAccessError
    from agents.researcher.source_collector import SourceCollector

    class _Rag:
        async def search(self, query: str, **kwargs):
            return []

    class _Web:
        async def run(self, query: str, max_results: int):
            return []

    collector = SourceCollector(_Rag(), _Web(), None, ResearcherConfig())  # type: ignore[arg-type]
    with pytest.raises(ResearchAccessError):
        asyncio.run(collector.collect("q", topic_scope=None, access_scope="tenant", context=""))


def test_source_collection_diagnostic() -> None:
    from agents.researcher.source_collector import SourceCollector

    class _RagBroken:
        async def search(self, query: str, **kwargs):
            raise TimeoutError("rag timeout")

    class _Web:
        async def run(self, query: str, max_results: int):
            return []

    collector = SourceCollector(_RagBroken(), _Web(), None, ResearcherConfig())  # type: ignore[arg-type]
    sources, diagnostics, _ = asyncio.run(
        collector.collect("q", topic_scope=None, access_scope="public", context="")
    )
    assert sources == []
    assert any(d.code == "rag_failed" for d in diagnostics)
