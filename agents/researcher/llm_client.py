from __future__ import annotations

import asyncio
import json
from json import JSONDecodeError
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agents.researcher.config import ResearcherConfig
from agents.researcher.errors import ResearchLLMError
from core.llm_router import LLMRouter
from schemas.research import ResearchFact

_MAX_REASK_OUTPUT_CHARS = 2000


class LLMResearchResponse(BaseModel):
    facts: list[ResearchFact] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class StructuredLLMClient:
    """Typed JSON client over LLMRouter."""

    def __init__(self, llm_router: LLMRouter, config: ResearcherConfig) -> None:
        self._router = llm_router
        self._config = config

    async def query(
        self, prompt: str, system_prompt: str, *, allowed_source_ids: set[str] | None = None
    ) -> LLMResearchResponse:
        parsed = await self.generate(prompt, system_prompt=system_prompt)
        try:
            response = LLMResearchResponse.model_validate(parsed)
        except ValidationError as exc:
            raise ResearchLLMError("schema_validation_failure") from exc

        if allowed_source_ids is not None:
            patched_facts: list[ResearchFact] = []
            for fact in response.facts:
                unknown = [sid for sid in fact.source_ids if sid not in allowed_source_ids]
                if unknown:
                    fact = fact.model_copy(
                        update={
                            "source_ids": [
                                sid for sid in fact.source_ids if sid in allowed_source_ids
                            ]
                        }
                    )
                patched_facts.append(fact)
            response = response.model_copy(update={"facts": patched_facts})
        return response

    async def generate(self, prompt: str, *, system_prompt: str) -> dict[str, Any]:
        attempts = max(1, int(self._config.retry_attempts))
        base_delay = max(0.0, float(self._config.retry_initial_delay))
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                return await self._generate_once(prompt, system_prompt=system_prompt)
            except TimeoutError as exc:
                last_error = exc
                if attempt >= attempts:
                    break
                await asyncio.sleep(base_delay * (2 ** (attempt - 1)))
        if last_error is not None:
            raise last_error
        raise ResearchLLMError("llm_generate_failed")

    async def _generate_once(self, prompt: str, *, system_prompt: str) -> dict[str, Any]:
        response = await self._query_router(prompt=prompt, system_prompt=system_prompt)
        parsed = self._parse_json(response.text)
        if parsed is not None:
            return parsed
        if not self._looks_like_json_candidate(response.text):
            raise ResearchLLMError("malformed_json")

        reask_limit = max(0, int(self._config.llm_reask_limit))
        invalid_output = response.text
        for _ in range(reask_limit):
            reask_prompt = self._build_reask_prompt(prompt=prompt, invalid_output=invalid_output)
            reask = await self._query_router(prompt=reask_prompt, system_prompt=system_prompt)
            reparsed = self._parse_json(reask.text)
            if reparsed is not None:
                return reparsed
            invalid_output = reask.text
        raise ResearchLLMError("malformed_json_after_reask")

    async def _query_router(self, *, prompt: str, system_prompt: str) -> Any:
        try:
            return await asyncio.wait_for(
                self._router.query(prompt=prompt, system_prompt=system_prompt),
                timeout=self._config.llm_timeout_seconds,
            )
        except StopAsyncIteration as exc:
            raise ResearchLLMError("llm_empty_response") from exc
        except Exception as exc:  # noqa: BLE001
            if isinstance(exc, (TimeoutError, asyncio.exceptions.TimeoutError)):
                raise TimeoutError("llm_timeout") from exc
            raise ResearchLLMError("llm_router_unavailable") from exc

    @staticmethod
    def _build_reask_prompt(*, prompt: str, invalid_output: str) -> str:
        clipped = invalid_output[:_MAX_REASK_OUTPUT_CHARS]
        return (
            "Требуется JSON-объект по схеме: "
            '{"facts":[{"text":"...","applicability":"","confidence":0.0,"source_ids":["..."],'
            '"evidence":[{"source_id":"...","quote":"...","locator":null}]}],"gaps":["..."]}.\n'
            "Используй исходный контекст ниже и исправь ответ.\n\n"
            f"Original prompt:\n{prompt[:4000]}\n\n"
            f"Invalid output:\n{clipped}\n\n"
            "Верни ТОЛЬКО JSON object, без markdown и пояснений."
        )

    @staticmethod
    def _parse_json(payload: str) -> dict[str, Any] | None:
        parsed = StructuredLLMClient._try_parse_object(payload)
        if parsed is not None:
            return parsed

        stripped = payload.strip()
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            if len(lines) >= 3 and lines[0].startswith("```") and lines[-1].strip() == "```":
                fenced_payload = "\n".join(lines[1:-1])
                if lines[0].strip().lower() in {"```json", "```json5", "```"}:
                    parsed = StructuredLLMClient._try_parse_object(fenced_payload.strip())
                    if parsed is not None:
                        return parsed

        decoder = json.JSONDecoder()
        for idx, char in enumerate(payload):
            if char != "{":
                continue
            try:
                obj, end = decoder.raw_decode(payload[idx:])
            except JSONDecodeError:
                continue
            if isinstance(obj, dict) and payload[idx + end :].strip() in {"", "```"}:
                return obj
            if isinstance(obj, dict):
                return obj
        return None

    @staticmethod
    def _try_parse_object(payload: str) -> dict[str, Any] | None:
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            return None
        if not isinstance(parsed, dict):
            return None
        return parsed

    @staticmethod
    def _looks_like_json_candidate(payload: str) -> bool:
        stripped = payload.strip()
        return "{" in stripped or stripped.startswith("```")
