from __future__ import annotations

import asyncio
import json
import uuid
import warnings
from time import perf_counter
from typing import Any

import structlog

from agents.base import BaseAgent
from agents.researcher.confidence import ConfidenceScorer
from agents.researcher.config import ResearcherConfig
from agents.researcher.domain import choose_primary_sources, diagnostics_for_sources
from agents.researcher.errors import (
    ResearchAccessError,
    ResearchLLMError,
    ResearchScopeError,
    ResearchSourceError,
    ResearchValidationError,
)
from agents.researcher.fact_validator import FactValidator
from agents.researcher.llm_client import LLMResearchResponse, StructuredLLMClient
from agents.researcher.prompt_builder import PromptBuilder
from agents.researcher.security import InjectionGuard
from agents.researcher.source_collector import SourceCollector
from api.metrics import (
    RESEARCHER_CACHE_HITS_TOTAL,
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
from schemas.research import Diagnostic, ResearchResponse

struct_logger = structlog.get_logger("agents.researcher")

_ALLOWED_ACCESS_SCOPES = {"public", "private", "tenant", "org", "project", "user"}


class ResearcherAgent(BaseAgent):
    """🔍 Researcher — thin orchestrator with strict fail-closed access."""

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

    @property
    def rag_engine(self) -> RAGEngine | None:
        return self._rag_engine

    @rag_engine.setter
    def rag_engine(self, value: RAGEngine | None) -> None:
        self._rag_engine = value
        self._collector = None

    @property
    def web_search_tool(self) -> WebSearchTool | None:
        return self._web_search_tool

    @web_search_tool.setter
    def web_search_tool(self, value: WebSearchTool | None) -> None:
        self._web_search_tool = value
        self._collector = None

    @property
    def cache(self) -> RedisCache | None:
        return self._cache

    @cache.setter
    def cache(self, value: RedisCache | None) -> None:
        self._cache = value
        self._collector = None

    async def _ensure_initialized(self) -> None:
        async with self._init_lock:
            if self._collector is None:
                self._config.rag_timeout_seconds = float(
                    getattr(
                        settings, "research_rag_timeout_seconds", self._config.rag_timeout_seconds
                    )
                )
                self._config.web_timeout_seconds = float(
                    getattr(
                        settings, "research_web_timeout_seconds", self._config.web_timeout_seconds
                    )
                )
                self._config.llm_timeout_seconds = float(
                    getattr(
                        settings, "research_llm_timeout_seconds", self._config.llm_timeout_seconds
                    )
                )
                rag_engine = self._rag_engine or RAGEngine()
                web_tool = self._web_search_tool or WebSearchTool()
                cache = await self._get_or_create_cache()
                self._collector = SourceCollector(
                    rag_engine, web_tool, cache, self._config, injection_guard=self._security
                )
                self._llm_client = StructuredLLMClient(self.llm_router, self._config)

    async def _get_or_create_cache(self) -> RedisCache | None:
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
        logger.info(
            "research_started", message=self._security.mask_pii(str(state.get("message", "")))
        )

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
        except (
            ResearchScopeError,
            ResearchAccessError,
            ResearchSourceError,
            ResearchLLMError,
            ResearchValidationError,
            ValueError,
            TypeError,
            KeyError,
        ) as exc:
            RESEARCHER_REQUESTS_TOTAL.labels(status="error").inc()
            logger.error("research_failed", error=str(exc), error_type=type(exc).__name__)
            code = getattr(exc, "code", type(exc).__name__)
            state["research_facts"] = "[]"
            state["research_payload"] = {
                "query": str(state.get("message", "")),
                "facts": [],
                "sources": [],
                "gaps": ["Внутренняя ошибка агента"],
                "diagnostics": [code],
                "diagnostics_struct": [
                    {
                        "code": code,
                        "message": str(exc),
                        "severity": "error",
                        "component": "researcher",
                        "stage": "orchestrate",
                    }
                ],
                "confidence_overall": 0.0,
            }
            return self._update_state(state, "")

    async def _orchestrate(
        self, state: dict[str, Any], logger: structlog.stdlib.BoundLogger
    ) -> dict[str, Any]:
        message = str(state.get("message", "")).strip()
        if not message:
            raise ValueError("Пустой запрос")

        topic_scope = str(state.get("topic_scope") or "").strip() or None
        access_scope = self._resolve_access_scope(state)

        context = str(state.get("context", "")).strip()
        user_id = state.get("user_id")
        org_id = state.get("org_id")
        tenant_id = state.get("tenant_id")
        project_id = state.get("project_id")

        sources, collection_diag, cache_hit = await self._collect_sources(
            message,
            topic_scope=topic_scope,
            access_scope=access_scope,
            context=context,
            user_id=user_id,
            org_id=org_id,
            tenant_id=tenant_id,
            project_id=project_id,
        )
        sources = choose_primary_sources(message, sources)
        collection_diag.extend(diagnostics_for_sources(sources))

        RESEARCHER_SOURCES_COUNT.observe(len(sources))
        if any(d.code == "web_fallback" for d in collection_diag):
            RESEARCHER_WEB_FALLBACK_TOTAL.inc()
        if cache_hit:
            RESEARCHER_CACHE_HITS_TOTAL.inc()

        prompt = PromptBuilder.build(message, context, sources, self._config)

        llm_diag: list[Diagnostic] = []
        llm_response = LLMResearchResponse(facts=[], gaps=[])
        llm_start = perf_counter()
        try:
            if self._llm_client is None:
                raise ResearchLLMError("llm_client_uninitialized")
            llm_response, llm_diag = await self._llm_client.query(
                prompt,
                PromptBuilder.system_prompt(self._config),
                allowed_source_ids={s.id for s in sources},
            )
        except TimeoutError:
            llm_diag.append(
                Diagnostic(
                    code="llm_timeout",
                    message="LLM timeout",
                    severity="error",
                    component="llm",
                    stage="llm",
                )
            )
        except (ResearchLLMError, ResearchValidationError) as exc:
            llm_diag.append(
                Diagnostic(
                    code=getattr(exc, "code", "llm_error"),
                    message=str(exc),
                    severity="error",
                    component="llm",
                    stage="llm",
                )
            )
        finally:
            RESEARCHER_LLM_DURATION_SECONDS.observe(perf_counter() - llm_start)

        validated_facts, validation_diag = self._validator.validate_facts(llm_response.facts, sources)

        confidence = self._scorer.compute(validated_facts, sources)
        gaps = list(dict.fromkeys(llm_response.gaps))
        if not validated_facts and sources and llm_response.facts:
            gaps.append("Факты не прошли валидацию источников")

        diag_struct = self._deduplicate_diagnostics([*collection_diag, *llm_diag, *validation_diag])
        diagnostics_legacy: list[str] = list(dict.fromkeys([d.code for d in diag_struct]))

        payload = ResearchResponse(
            query=message,
            facts=validated_facts,
            sources=sources,
            gaps=gaps,
            diagnostics=diagnostics_legacy,
            diagnostics_struct=diag_struct,
            confidence_overall=confidence.overall,
            confidence_breakdown=confidence.model_dump(),
        )

        safe_facts_artifact = json.dumps([fact.model_dump() for fact in validated_facts], ensure_ascii=False)
        state["research_facts"] = safe_facts_artifact
        state["research_payload"] = payload.model_dump()
        logger.info("research_orchestrated", diagnostics=len(diag_struct), facts=len(validated_facts))
        return self._update_state(state, safe_facts_artifact)

    async def _collect_sources(self, message: str, **kwargs: Any) -> tuple[list, list[Diagnostic], bool]:
        await self._ensure_initialized()
        if self._collector is None:
            raise ResearchSourceError("collector_not_initialized")
        return await self._collector.collect(message, **kwargs)

    @staticmethod
    def _deduplicate_diagnostics(diags: list[Diagnostic]) -> list[Diagnostic]:
        seen: set[tuple[str, str, str, str | None, str | None]] = set()
        out: list[Diagnostic] = []
        for item in diags:
            key = (item.code, item.message, item.component, item.source_id, item.fact_id)
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
        return out

    @staticmethod
    def _resolve_access_scope(state: dict[str, Any]) -> str:
        explicit_provided = "access_scope" in state
        explicit_value = state.get("access_scope")
        if explicit_provided and explicit_value is None:
            return "public"
        if explicit_provided and isinstance(explicit_value, str) and not explicit_value.strip():
            raise ResearchScopeError("empty access_scope is forbidden")
        if explicit_provided:
            return ResearcherAgent._validate_access_scope(str(explicit_value))

        for legacy_key in ("scope", "role"):
            if legacy_key in state:
                warnings.warn(
                    f"Key '{legacy_key}' is deprecated for ResearcherAgent; use 'access_scope' instead.",
                    DeprecationWarning,
                    stacklevel=3,
                )
                return ResearcherAgent._validate_access_scope(str(state.get(legacy_key)))
        return "public"

    @staticmethod
    def _validate_access_scope(scope: str | None) -> str:
        if scope is None:
            return "public"
        normalized = scope.strip().lower()
        if not normalized:
            raise ResearchScopeError("empty access_scope is forbidden")
        if normalized not in _ALLOWED_ACCESS_SCOPES:
            raise ResearchScopeError(f"unknown access_scope={scope}")
        return normalized
