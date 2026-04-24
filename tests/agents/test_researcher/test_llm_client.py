import asyncio

import pytest

from agents.researcher.config import ResearcherConfig
from agents.researcher.errors import ResearchLLMError, ResearchValidationError
from agents.researcher.llm_client import StructuredLLMClient


class _Resp:
    def __init__(self, text: str) -> None:
        self.text = text


class _Router:
    def __init__(self, responses: list[str], *, delay: float = 0.0, fail: bool = False) -> None:
        self._responses = responses
        self.delay = delay
        self.fail = fail
        self.calls = 0

    async def query(self, prompt: str, system_prompt: str):
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise RuntimeError("router down")
        if self.calls > len(self._responses):
            return _Resp(self._responses[-1])
        return _Resp(self._responses[self.calls - 1])


def test_invalid_json_returns_malformed_error() -> None:
    client = StructuredLLMClient(_Router(["not-json", "still not"]), ResearcherConfig(llm_reask_limit=1))  # type: ignore[arg-type]
    with pytest.raises(ResearchLLMError) as exc:
        asyncio.run(client.generate("p", system_prompt="s"))
    assert exc.value.code == "llm_malformed_json"


def test_invalid_schema_raises_validation_error() -> None:
    client = StructuredLLMClient(_Router(['{"facts": "oops", "gaps": []}']), ResearcherConfig())  # type: ignore[arg-type]
    with pytest.raises(ResearchValidationError) as exc:
        asyncio.run(client.query("p", "s"))
    assert exc.value.code == "llm_schema_validation_failure"


def test_extra_fields_rejected() -> None:
    client = StructuredLLMClient(_Router(['{"facts": [], "gaps": [], "x": 1}']), ResearcherConfig())  # type: ignore[arg-type]
    with pytest.raises(ResearchValidationError):
        asyncio.run(client.query("p", "s"))


def test_hallucinated_source_id_generates_diagnostic() -> None:
    payload = '{"facts": [{"text":"x","applicability":"","confidence":0.1,"source_ids":["fake"]}], "gaps": []}'
    client = StructuredLLMClient(_Router([payload]), ResearcherConfig())  # type: ignore[arg-type]
    response, diags = asyncio.run(client.query("p", "s", allowed_source_ids={"s1"}))
    assert response.facts[0].source_ids == []
    assert any(d.code == "llm_hallucinated_source_id" for d in diags)


def test_reask_limit_respected() -> None:
    client = StructuredLLMClient(_Router(["bad", "bad2", "bad3"]), ResearcherConfig(llm_reask_limit=1))  # type: ignore[arg-type]
    with pytest.raises(ResearchLLMError):
        asyncio.run(client.generate("p", system_prompt="s"))


def test_timeout_distinct_from_malformed_json() -> None:
    client = StructuredLLMClient(
        _Router(['{"facts": [], "gaps": []}'], delay=0.02),
        ResearcherConfig(llm_timeout_seconds=0.001, retry_attempts=1),
    )  # type: ignore[arg-type]
    with pytest.raises(TimeoutError):
        asyncio.run(client.generate("p", system_prompt="s"))
