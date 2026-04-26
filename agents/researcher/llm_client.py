from __future__ import annotations

import asyncio
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agents.researcher.config import ResearcherConfig
from agents.researcher.errors import ResearchLLMError, ResearchValidationError
from core.llm_router import LLMRouter
from schemas.research import Diagnostic, ResearchEvidence, ResearchFact

_MAX_REASK_OUTPUT_CHARS = 2000


class LLMResearchEvidence(BaseModel):
    source_id: str
    quote: str
    locator: str | None = None
    chunk_id: str | None = None
    document_id: str | None = None
    page: int | None = None
    support_status: str | None = None

    model_config = ConfigDict(extra="forbid")


class LLMResearchFact(BaseModel):
    text: str
    applicability: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_ids: list[str] = Field(default_factory=list)
    evidence: list[LLMResearchEvidence] = Field(default_factory=list)
    support_status: str | None = None

    model_config = ConfigDict(extra="forbid")


class LLMResearchResponse(BaseModel):
    facts: list[LLMResearchFact] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class StructuredLLMClient:
    """Typed JSON client over LLMRouter."""

    def __init__(self, llm_router: LLMRouter, config: ResearcherConfig) -> None:
        self._router = llm_router
        self._config = config

    async def query(
        self,
        prompt: str,
        system_prompt: str,
        *,
        allowed_source_ids: set[str] | None = None,
    ) -> tuple[LLMResearchResponse, list[Diagnostic]]:
        parsed = await self.generate(prompt, system_prompt=system_prompt)
        diagnostics: list[Diagnostic] = []
        try:
            response = LLMResearchResponse.model_validate(parsed)
        except ValidationError as exc:
            raise ResearchValidationError(
                "llm_schema_validation_failure",
                "schema_validation_failure",
                details={"errors": exc.errors()},
            ) from exc

        if allowed_source_ids is not None:
            patched_facts: list[LLMResearchFact] = []
            for idx, fact in enumerate(response.facts, start=1):
                unknown = [
                    sid for sid in fact.source_ids if sid not in allowed_source_ids
                ]
                allowed_evidence = [
                    e for e in fact.evidence if e.source_id in allowed_source_ids
                ]
                if unknown:
                    diagnostics.append(
                        Diagnostic(
                            code="llm_hallucinated_source_id",
                            message=f"fact#{idx}: unknown source_ids={unknown}",
                            severity="warn",
                            component="llm",
                            stage="llm",
                        )
                    )
                    fact = fact.model_copy(
                        update={
                            "source_ids": [
                                sid
                                for sid in fact.source_ids
                                if sid in allowed_source_ids
                            ],
                            "evidence": allowed_evidence,
                        }
                    )
                elif len(allowed_evidence) != len(fact.evidence):
                    diagnostics.append(
                        Diagnostic(
                            code="llm_evidence_unknown_source_id",
                            message=f"fact#{idx}: evidence references unknown source",
                            severity="warn",
                            component="llm",
                            stage="llm",
                        )
                    )
                    fact = fact.model_copy(update={"evidence": allowed_evidence})
                if fact.source_ids and not fact.evidence:
                    diagnostics.append(
                        Diagnostic(
                            code="llm_source_without_evidence",
                            message=f"fact#{idx}: source_ids without evidence",
                            severity="warn",
                            component="llm",
                            stage="llm",
                        )
                    )
                    fact = fact.model_copy(update={"source_ids": []})
                patched_facts.append(fact)
            response = response.model_copy(update={"facts": patched_facts})
        try:
            mapped_facts = [
                ResearchFact(
                    text=f.text,
                    applicability=f.applicability,
                    confidence=f.confidence,
                    source_ids=f.source_ids,
                    support_status=f.support_status,  # type: ignore[arg-type]
                    evidence=[
                        ResearchEvidence(
                            source_id=e.source_id,
                            quote=e.quote,
                            locator=e.locator,
                            chunk_id=e.chunk_id,
                            document_id=e.document_id,
                            page=e.page,
                            support_status=e.support_status,  # type: ignore[arg-type]
                        )
                        for e in f.evidence
                    ],
                )
                for f in response.facts
            ]
        except ValidationError as exc:
            raise ResearchValidationError(
                "llm_schema_validation_failure",
                "schema_validation_failure",
                details={"errors": exc.errors()},
            ) from exc
        return response.model_copy(update={"facts": mapped_facts}), diagnostics  # type: ignore[arg-type]

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

    async def _generate_once(
        self, prompt: str, *, system_prompt: str
    ) -> dict[str, Any]:
        response = await self._query_router(prompt=prompt, system_prompt=system_prompt)
        parsed = self._parse_json(response.text)
        if parsed is not None:
            return parsed
        stripped = response.text.strip()
        if (
            "{" in stripped
            and not stripped.startswith("{")
            and not stripped.startswith("```")
        ):
            raise ResearchLLMError("llm_non_json_envelope")
        if not self._looks_like_json_candidate(response.text):
            raise ResearchLLMError("llm_malformed_json")

        reask_limit = max(0, int(self._config.llm_reask_limit))
        invalid_output = response.text
        for _ in range(reask_limit):
            reask_prompt = self._build_reask_prompt(
                prompt=prompt,
                invalid_output=invalid_output,
                json_schema=self._config.llm_reask_schema,
            )
            reask = await self._query_router(
                prompt=reask_prompt, system_prompt=system_prompt
            )
            reparsed = self._parse_json(reask.text)
            if reparsed is not None:
                return reparsed
            invalid_output = reask.text
        raise ResearchLLMError("llm_malformed_json")

    async def _query_router(self, *, prompt: str, system_prompt: str) -> Any:
        try:
            return await asyncio.wait_for(
                self._router.query(prompt=prompt, system_prompt=system_prompt),
                timeout=self._config.llm_timeout_seconds,
            )
        except StopAsyncIteration as exc:
            raise ResearchLLMError("llm_empty_response") from exc
        except Exception as exc:  # noqa: BLE001
            if isinstance(exc, TimeoutError | asyncio.exceptions.TimeoutError):
                raise TimeoutError("llm_timeout") from exc
            raise ResearchLLMError("llm_router_unavailable") from exc

    @staticmethod
    def _build_reask_prompt(
        *, prompt: str, invalid_output: str, json_schema: str
    ) -> str:
        clipped = invalid_output[:_MAX_REASK_OUTPUT_CHARS]
        return (
            "Требуется JSON-объект по схеме: "
            f"{json_schema}.\n"
            "Используй исходный контекст ниже и исправь ответ.\n\n"
            f"Original prompt:\n{prompt[:4000]}\n\n"
            f"Invalid output:\n{clipped}\n\n"
            "Верни ТОЛЬКО JSON object, без markdown и пояснений."
        )

    def _parse_json(self, payload: str) -> dict[str, Any] | None:
        parsed = self._try_parse_object(payload)
        if parsed is not None:
            return parsed

        stripped = payload.strip()
        if self._config.allow_fenced_json_output and stripped.startswith("```"):
            lines = stripped.splitlines()
            if (
                len(lines) >= 3
                and lines[0].startswith("```")
                and lines[-1].strip() == "```"
            ):
                fenced_payload = "\n".join(lines[1:-1])
                if lines[0].strip().lower() in {"```json", "```json5", "```"}:
                    parsed = self._try_parse_object(fenced_payload.strip())
                    if parsed is not None:
                        return parsed

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
