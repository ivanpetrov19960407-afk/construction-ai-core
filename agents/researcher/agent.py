from __future__ import annotations

import asyncio
import uuid
from time import perf_counter
from typing import Any

import structlog

from agents.base import BaseAgent
from agents.researcher.config import ResearcherConfig
from agents.researcher.confidence import ConfidenceScorer
from agents.researcher.fact_validator import FactValidator
from agents.researcher.llm_client import StructuredLLMClient
from agents.researcher.prompt_builder import PromptBuilder
from agents.researcher.security import InjectionGuard
from agents.researcher.source_collector import SourceCollector
from api.metrics import (
    RESEARCHER_CACHE_HITS_TOTAL,
    RESEARCHER_INJECTION_DETECTED_TOTAL,
    RESEARCHER_LLM_DURATION_SECONDS,
    RESEARCHER_REQUESTS_TOTAL,
    RESEARCHER_SOURCES_COUNT,
    RESEARCHER_WEB_FALLBACK_TOTAL,
)
from config.settings import settings
from core.cache import RedisCache
from core.llm_router import LLMRouter
from core.rag_engine import RAGEngine
from core.tools.web_search import WebSearchTool
from schemas.research import ResearchResponse

struct_logger = structlog.get_logger("agents.researcher")

_ALLOWED_ACCESS_SCOPES = {"admin", "pto_engineer", "foreman", "tender_specialist", "public"}


class ResearcherAgent(BaseAgent):
    """🔍 Researcher — thin production orchestrator."""

    def __init__(
        self,
        llm_router: LLMRouter,
        rag_engine: RAGEngine | None = None,
        web_search_tool: WebSearchTool | None = None,
        cache: RedisCache | None = None,
        config: ResearcherConfig | None = None,
    ) -> None:
        super().__init__(agent_id="01", llm_router=llm_router)
        self._config = config or ResearcherConfig()
        self._rag_engine = rag_engine
        self._web_search_tool = web_search_tool
        self._cache = cache
        self._collector: SourceCollector | None = None
        self._llm_client: StructuredLLMClient | None = None
        self._validator = FactValidator(self._config.fact_citation_min_similarity)
        self._scorer = ConfidenceScorer(self._config)
        self._security = InjectionGuard(self._config)
        self._cache_lock = asyncio.Lock()
        self._init_lock = asyncio.Lock()

    async def _ensure_initialized(self) -> None:
        """Lazy async DI init (no race conditions)."""
        async with self._init_lock:
            if self._collector is None:
                rag_engine = self._rag_engine or RAGEngine()
                web_tool = self._web_search_tool or WebSearchTool()
                cache = await self._get_or_create_cache()
                self._collector = SourceCollector(rag_engine, web_tool, cache, self._config)
                self._llm_client = StructuredLLMClient(self.llm_router, self._config)

    async def _get_or_create_cache(self) -> RedisCache | None:
        """Lazy cache creation."""
        if self._cache is not None:
            return self._cache
        async with self._cache_lock:
            if self._cache is None:
                try:
                    self._cache = RedisCache(settings.redis_url)
                except Exception as exc:  # noqa: BLE001
                    struct_logger.warning("cache_init_failed", error=str(exc))
                    self._cache = None
        return self._cache

    async def _run(self, state: dict[str, Any]) -> dict[str, Any]:
        started = perf_counter()
        trace_id = state.setdefault("trace_id", str(uuid.uuid4()))
        logger = struct_logger.bind(agent="researcher", trace_id=trace_id, agent_id=self.agent_id)

        RESEARCHER_REQUESTS_TOTAL.labels(status="started").inc()
        logger.info("research_started", message=self._security.mask_pii(str(state.get("message", ""))))

        try:
            await self._ensure_initialized()
            result = await self._orchestrate(state, logger)
            RESEARCHER_REQUESTS_TOTAL.labels(status="success").inc()
            logger.info(
                "research_completed",
                duration_ms=round((perf_counter() - started) * 1000, 2),
                sources_count=len(result.get("research_payload", {}).get("sources", [])),
            )
            return result
        except Exception as exc:  # noqa: BLE001
            RESEARCHER_REQUESTS_TOTAL.labels(status="error").inc()
            logger.error("research_failed", error=str(exc))
            state["research_facts"] = ""
            state["research_payload"] = {
                "facts": [],
                "sources": [],
                "gaps": ["Внутренняя ошибка агента"],
                "diagnostics": ["internal_error"],
            }
            return state

    async def _orchestrate(self, state: dict[str, Any], logger: structlog.stdlib.BoundLogger) -> dict[str, Any]:
        """Thin orchestration: collector → prompt → llm → validate → score."""
        message = str(state.get("message", "")).strip()
        if not message:
            raise ValueError("Пустой запрос")

        topic_scope = str(state.get("topic_scope") or "").strip() or None
        raw_scope = str(state.get("access_scope") or state.get("scope") or state.get("role") or "").strip() or None
        access_scope = self._validate_access_scope(raw_scope)
        context = str(state.get("context", "")).strip()
        user_id = state.get("user_id")

        retrieval_query = self._build_retrieval_query(message, topic_scope, context)

        assert self._collector is not None, "Collector not initialized"
        assert self._llm_client is not None, "LLM client not initialized"

        sources, collection_diag = await self._collector.collect(
            retrieval_query,
            topic_scope=topic_scope,
            access_scope=access_scope,
            context=context,
            user_id=user_id,
        )
        RESEARCHER_SOURCES_COUNT.observe(len(sources))
        if any(d.code == "web_fallback" for d in collection_diag):
            RESEARCHER_WEB_FALLBACK_TOTAL.inc()
        if not collection_diag:
            RESEARCHER_CACHE_HITS_TOTAL.inc()

        prompt = PromptBuilder.build(message, context, sources)

        llm_start = perf_counter()
        llm_response = await self._llm_client.query(prompt, PromptBuilder.SYSTEM_PROMPT)
        RESEARCHER_LLM_DURATION_SECONDS.observe(perf_counter() - llm_start)

        validated_facts, validation_diag = self._validator.validate(llm_response.facts, sources)

        suspicious = any(self._security._contains_prompt_injection(s.snippet or "") for s in sources)
        if suspicious:
            RESEARCHER_INJECTION_DETECTED_TOTAL.inc()

        confidence = self._scorer.compute(validated_facts, sources)

        gaps = list(dict.fromkeys(llm_response.gaps))
        if not validated_facts and sources:
            gaps.append("Факты не прошли валидацию источников")

        diagnostics_legacy = list(
            dict.fromkeys(
                [d.code for d in (*collection_diag, *validation_diag)]
                + (["prompt_injection_detected"] if suspicious else [])
            )
        )

        payload = ResearchResponse(
            query=message,
            facts=validated_facts,
            sources=sources,
            gaps=gaps,
            diagnostics=diagnostics_legacy,
            confidence_overall=confidence.overall,
            confidence_breakdown=confidence.model_dump(),
        )

        state["research_facts"] = llm_response.model_dump_json()
        state["research_payload"] = payload.model_dump()
        return state

    async def run_standalone(
        self,
        message: str,
        *,
        scope: str | None = None,
        context: str = "",
        user_id: str | None = None,
    ) -> ResearchResponse:
        """Standalone — 100% backward compat."""
        await self._ensure_initialized()
        state: dict[str, Any] = {
            "message": message,
            "scope": scope,
            "access_scope": scope,
            "topic_scope": scope,
            "context": context,
            "user_id": user_id,
            "history": [],
        }
        result = await self._run(state)
        return ResearchResponse.model_validate(result["research_payload"])

    @staticmethod
    def _validate_access_scope(scope: str | None) -> str | None:
        if scope and scope in _ALLOWED_ACCESS_SCOPES:
            return scope
        return None

    @staticmethod
    def _build_retrieval_query(message: str, topic_scope: str | None, context: str) -> str:
        parts = [message]
        if topic_scope:
            parts.append(f"Тема: {topic_scope}")
        if context:
            parts.append(f"Контекст: {context}")
        return "\n".join(parts).strip()
