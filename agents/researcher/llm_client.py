from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

try:
    from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter
except Exception:  # pragma: no cover
    def retry(**kwargs):
        _ = kwargs

        def decorator(fn):
            return fn

        return decorator

    def retry_if_exception_type(exc):
        return exc

    def stop_after_attempt(attempts):
        return attempts

    def wait_exponential_jitter(initial: float, max: float):
        _ = (initial, max)
        return None

from agents.researcher.config import ResearcherConfig
from core.llm_router import LLMRouter
from schemas.research import ResearchFact


class LLMResearchResponse(BaseModel):
    facts: list[ResearchFact] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class StructuredLLMClient:
    """Typed JSON client over LLMRouter."""

    def __init__(self, llm_router: LLMRouter, config: ResearcherConfig) -> None:
        self._router = llm_router
        self._config = config

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=0.5, max=4),
        retry=retry_if_exception_type((TimeoutError,)),
        reraise=True,
    )
    async def query(self, prompt: str, system_prompt: str) -> LLMResearchResponse:
        parsed = await self.generate(prompt, system_prompt=system_prompt)
        return LLMResearchResponse.model_validate(parsed)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=0.5, max=4),
        retry=retry_if_exception_type((TimeoutError,)),
        reraise=True,
    )
    async def generate(self, prompt: str, *, system_prompt: str) -> dict[str, Any]:
        try:
            response = await self._router.query(prompt=prompt, system_prompt=system_prompt)
        except StopAsyncIteration as exc:
            raise ValueError("llm_empty_response") from exc
        parsed = self._parse_json(response.text)
        if parsed is not None:
            return parsed
        if "{" not in response.text:
            raise ValueError("invalid_json_no_reask")

        reask_prompt = (
            "Return ONLY valid JSON object with keys facts and gaps. "
            f"Previous output was invalid:\n{response.text}"
        )
        try:
            reask = await self._router.query(prompt=reask_prompt, system_prompt=system_prompt)
        except StopAsyncIteration as exc:
            raise ValueError("llm_empty_response") from exc
        reparsed = self._parse_json(reask.text)
        if reparsed is None:
            raise ValueError("invalid_json_after_reask")
        return reparsed

    @staticmethod
    def _parse_json(payload: str) -> dict[str, Any] | None:
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            return None
        if not isinstance(parsed, dict):
            return None
        return parsed
