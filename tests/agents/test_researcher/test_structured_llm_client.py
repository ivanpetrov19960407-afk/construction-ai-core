import asyncio

import pytest

from agents.researcher.config import ResearcherConfig
from agents.researcher.llm_client import StructuredLLMClient


class _Resp:
    def __init__(self, text: str) -> None:
        self.text = text


class _Router:
    def __init__(self) -> None:
        self.calls = 0

    async def query(self, prompt: str, system_prompt: str):
        _ = (prompt, system_prompt)
        self.calls += 1
        if self.calls == 1:
            return _Resp("not-json")
        return _Resp('{"facts": [], "gaps": []}')


def test_structured_llm_client_reask_on_invalid_json() -> None:
    client = StructuredLLMClient(_Router(), ResearcherConfig())  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        asyncio.run(client.generate("prompt", system_prompt="sys"))
