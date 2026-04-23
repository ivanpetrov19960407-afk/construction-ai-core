import asyncio

import pytest

from agents.researcher.config import ResearcherConfig
from agents.researcher.llm_client import StructuredLLMClient


class _Resp:
    def __init__(self, text: str) -> None:
        self.text = text


class _Router:
    def __init__(self, responses: list[str], *, delay: float = 0.0) -> None:
        self._responses = responses
        self.delay = delay
        self.calls = 0

    async def query(self, prompt: str, system_prompt: str):
        _ = (prompt, system_prompt)
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.calls > len(self._responses):
            return _Resp(self._responses[-1])
        return _Resp(self._responses[self.calls - 1])


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ('{"facts": [], "gaps": []}', True),
        ("```json\n{\"facts\": [], \"gaps\": []}\n```", True),
        ("prefix text\n{\"facts\": [], \"gaps\": []}\nsuffix", True),
        ("[]", False),
        ("nope", False),
    ],
)
def test_parse_json_variants(payload: str, expected: bool) -> None:
    parsed = StructuredLLMClient._parse_json(payload)
    assert (parsed is not None) is expected


def test_structured_llm_client_reask_preserves_success() -> None:
    router = _Router(["not-json", '{"facts": [], "gaps": []}'])
    client = StructuredLLMClient(router, ResearcherConfig())  # type: ignore[arg-type]
    result = asyncio.run(client.generate("prompt", system_prompt="sys"))
    assert result == {"facts": [], "gaps": []}
    assert router.calls == 2


def test_structured_llm_client_timeout() -> None:
    router = _Router(['{"facts": [], "gaps": []}'], delay=0.03)
    cfg = ResearcherConfig(llm_timeout_seconds=0.001, retry_attempts=1)
    client = StructuredLLMClient(router, cfg)  # type: ignore[arg-type]
    with pytest.raises(TimeoutError):
        asyncio.run(client.generate("prompt", system_prompt="sys"))


def test_structured_llm_client_respects_retry_attempts() -> None:
    router = _Router(['{"facts": [], "gaps": []}'], delay=0.02)
    cfg = ResearcherConfig(llm_timeout_seconds=0.001, retry_attempts=2, retry_initial_delay=0.0)
    client = StructuredLLMClient(router, cfg)  # type: ignore[arg-type]
    with pytest.raises(TimeoutError):
        asyncio.run(client.generate("prompt", system_prompt="sys"))
    assert router.calls == 2
