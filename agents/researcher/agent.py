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
from agents.researcher.errors import ResearchAccessError, ResearchLLMError, ResearchScopeError, ResearchSourceError
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
from schemas.research import Diagnostic, ResearchFact, ResearchResponse, ResearchSource

struct_logger = structlog.get_logger("agents.researcher")

_ALLOWED_ACCESS_SCOPES = {"public", "private", "tenant", "org", "project", "user"}
_LEGACY_ROLE_SCOPE_MAP = {
    "admin": "public",
    "pto_engineer": "public",
    "foreman": "public",
    "tender_specialist": "public",
}


class ResearcherAgent(BaseAgent):
    """🔍 Researcher — production orchestrator with strict fail-closed access."""

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
                self._config.rag_timeout_seconds = float(getattr(settings, "research_rag_timeout_seconds", self._config.rag_timeout_seconds))
                self._config.web_timeout_seconds = float(getattr(settings, "research_web_timeout_seconds", self._config.web_timeout_seconds))
                self._config.llm_timeout_seconds = float(getattr(settings, "research_llm_timeout_seconds", self._config.llm_timeout_seconds))
                rag_engine = self._rag_engine or RAGEngine()
                web_tool = self._web_search_tool or WebSearchTool()
                cache = await self._get_or_create_cache()
                self._collector = SourceCollector(rag_engine, web_tool, cache, self._config, injection_guard=self._security)
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
        logger.info("research_started", message=self._security.mask_pii(str(state.get("message", ""))))

        try:
            await self._ensure_initialized()
            result = await self._orchestrate(state, logger)
            RESEARCHER_REQUESTS_TOTAL.labels(status="success").inc()
            logger.info("research_completed", duration_ms=round((perf_counter() - started) * 1000, 2), sources_count=len(result.get("research_payload", {}).get("sources", [])))
            return result
        except (ResearchScopeError, ResearchAccessError, ResearchSourceError, ResearchLLMError, ValueError, TypeError, KeyError) as exc:
            RESEARCHER_REQUESTS_TOTAL.labels(status="error").inc()
            logger.error("research_failed", error=str(exc), error_type=type(exc).__name__)
            state["research_facts"] = "[]"
            state["research_payload"] = {
                "query": str(state.get("message", "")),
                "facts": [],
                "sources": [],
                "gaps": ["Внутренняя ошибка агента"],
                "diagnostics": [type(exc).__name__],
                "diagnostics_struct": [
                    {
                        "code": type(exc).__name__,
                        "message": str(exc),
                        "severity": "error",
                        "component": "researcher",
                    }
                ],
                "confidence_overall": 0.0,
            }
            return self._update_state(state, "")
        except Exception as exc:  # noqa: BLE001
            RESEARCHER_REQUESTS_TOTAL.labels(status="error").inc()
            struct_logger.exception("research_unexpected_error", error=str(exc))
            raise

    async def _orchestrate(self, state: dict[str, Any], logger: structlog.stdlib.BoundLogger) -> dict[str, Any]:
        message = str(state.get("message", "")).strip()
        if not message:
            raise ValueError("Пустой запрос")

        topic_scope = str(state.get("topic_scope") or "").strip() or None

        explicit_access = str(state.get("access_scope") or "").strip() or None
        legacy_scope = str(state.get("scope") or state.get("role") or "").strip() or None
        if explicit_access is None and legacy_scope is not None:
            warnings.warn(
                "Keys 'scope' and 'role' are deprecated for ResearcherAgent; use 'access_scope' instead.",
                DeprecationWarning,
                stacklevel=3,
            )
        raw_scope = explicit_access or legacy_scope
        if explicit_access is None and legacy_scope in _LEGACY_ROLE_SCOPE_MAP:
            raw_scope = _LEGACY_ROLE_SCOPE_MAP[legacy_scope]
        access_scope = self._validate_access_scope(raw_scope)
        context = str(state.get("context", "")).strip()
        user_id = state.get("user_id")
        org_id = state.get("org_id")
        tenant_id = state.get("tenant_id")
        project_id = state.get("project_id")

        sources, raw_collection_diag, cache_hit = await self._collect_sources(
            message,
            topic_scope=topic_scope,
            access_scope=access_scope,
            context=context,
            user_id=user_id,
            org_id=org_id,
            tenant_id=tenant_id,
            project_id=project_id,
        )

        collection_diag: list[Diagnostic] = []
        for item in raw_collection_diag:
            if isinstance(item, Diagnostic):
                collection_diag.append(item)
            else:
                collection_diag.append(
                    Diagnostic(
                        code=str(item),
                        message=str(item),
                        severity="warn",
                        component="source_collector",
                    )
                )

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
            llm_response = await self._llm_client.query(
                prompt,
                PromptBuilder.SYSTEM_PROMPT,
                allowed_source_ids={s.id for s in sources},
            )
        except TimeoutError:
            llm_diag.append(Diagnostic(code="llm_timeout", message="LLM timeout", severity="error", component="llm"))
        except ResearchLLMError as exc:
            llm_diag.append(Diagnostic(code="llm_error", message=str(exc), severity="error", component="llm"))
            llm_diag.append(
                Diagnostic(
                    code="llm_error_legacy",
                    message="LLM вернул ответ не в JSON-формате",
                    severity="error",
                    component="llm",
                )
            )
        finally:
            RESEARCHER_LLM_DURATION_SECONDS.observe(perf_counter() - llm_start)

        validated_facts, validation_diag = self._validator.validate_facts(llm_response.facts, sources)

        confidence = self._scorer.compute(validated_facts, sources)
        gaps = list(dict.fromkeys(llm_response.gaps))
        if not validated_facts and sources and llm_response.facts:
            gaps.append("Факты не прошли валидацию источников")

        seen_diag: set[tuple[str, str, str, str | None]] = set()
        diag_struct: list[Diagnostic] = []
        for item in [*collection_diag, *llm_diag, *validation_diag]:
            key = (item.code, item.message, item.component, item.source_id)
            if key in seen_diag:
                continue
            seen_diag.add(key)
            diag_struct.append(item)
        diagnostics_legacy: list[str] = []
        for d in diag_struct:
            diagnostics_legacy.append(d.code)
            diagnostics_legacy.append(d.message)
            diagnostics_legacy.append(f"{d.code}:{d.message}")
        diagnostics_legacy = list(dict.fromkeys(diagnostics_legacy))

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
        return self._update_state(state, safe_facts_artifact)

    async def _collect_sources(
        self,
        message: str,
        *,
        topic_scope: str | None,
        access_scope: str,
        context: str,
        user_id: str | None = None,
        org_id: str | None = None,
        tenant_id: str | None = None,
        project_id: str | None = None,
    ) -> tuple[list, list[str], bool]:
        await self._ensure_initialized()
        if self._collector is None:
            raise ResearchSourceError("collector_not_initialized")
        sources, diagnostics, cache_hit = await self._collector.collect(
            message,
            topic_scope=topic_scope,
            access_scope=access_scope,
            context=context,
            user_id=user_id,
            org_id=org_id,
            tenant_id=tenant_id,
            project_id=project_id,
        )
        legacy: list[str] = []
        for item in diagnostics:
            if item.code == "rag_failed" and item.message == "TimeoutError":
                legacy.append("rag_timeout")
            elif item.code == "rag_failed":
                legacy.append(f"rag_failed:{item.message}")
            else:
                legacy.append(item.code)
        return sources, list(dict.fromkeys(legacy)), cache_hit

    async def run_standalone(self, message: str, *, scope: str | None = None, context: str = "", user_id: str | None = None) -> ResearchResponse:
        await self._ensure_initialized()
        state: dict[str, Any] = {
            "message": message,
            "scope": scope,
            "access_scope": scope,
            "topic_scope": None,
            "context": context,
            "user_id": user_id,
            "history": [],
        }
        result = await self._run(state)
        return ResearchResponse.model_validate(result["research_payload"])

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

    @staticmethod
    def _sanitize_source_snippet(snippet: str) -> str:
        sanitized, _ = InjectionGuard.sanitize_snippet(snippet)
        if sanitized == "[REDACTED: suspected prompt injection]":
            return "[sanitized potential prompt-injection snippet]"
        return sanitized

    @staticmethod
    def _parse_llm_json(query: str, raw: str, sources: list[ResearchSource]) -> ResearchResponse:
        from agents.researcher.llm_client import StructuredLLMClient

        payload = StructuredLLMClient._parse_json(raw)
        diagnostics: list[str] = []
        if payload is None:
            payload = {}
            diagnostics = ["llm_invalid_json"]
        facts: list[ResearchFact] = []
        for fact in payload.get("facts", []):
            try:
                facts.append(ResearchFact.model_validate(fact))
            except Exception:
                continue
        return ResearchResponse(
            query=query,
            facts=facts,
            sources=sources,
            gaps=[str(x) for x in payload.get("gaps", [])],
            diagnostics=diagnostics,
            confidence_overall=ResearcherAgent._compute_confidence_overall(facts, sources),
        )

    @staticmethod
    def _validate_fact_source_ids(
        facts: list[ResearchFact], sources: list[ResearchSource]
    ) -> tuple[list[ResearchFact], list[str]]:
        known = {s.id for s in sources}
        out: list[ResearchFact] = []
        diagnostics: list[str] = []
        for idx, fact in enumerate(facts, start=1):
            valid = [sid for sid in fact.source_ids if sid in known]
            if not valid:
                diagnostics.append(f"Факт #{idx} отброшен: нет валидных source_ids")
                continue
            if len(valid) != len(fact.source_ids):
                diagnostics.append(f"Факт #{idx}: удалены невалидные source_ids")
            out.append(fact.model_copy(update={"source_ids": valid}))
        return out, diagnostics

    def _need_web_fallback(self, rag_sources: list[ResearchSource]) -> bool:
        min_sources = int(getattr(settings, "research_web_min_rag_sources", self._config.web_min_rag_sources))
        min_avg = float(getattr(settings, "research_web_min_avg_score", self._config.web_min_avg_score))
        min_chars = int(getattr(settings, "research_web_min_snippet_chars", 5))
        if len(rag_sources) < min_sources:
            return True
        avg = sum(s.score for s in rag_sources) / max(len(rag_sources), 1)
        total_chars = sum(len(s.snippet or "") for s in rag_sources)
        return avg < min_avg or total_chars < min_chars

    @staticmethod
    def _normalize_rag_score(chunk: dict[str, Any]) -> float:
        score = float(chunk.get("score", 0.0) or 0.0)
        score_type = str(chunk.get("score_type", "") or "")
        if score_type == "distance":
            return max(0.0, min(1.0, 1.0 - (score if score <= 1 else score / 5)))
        if score > 1:
            score = score / 100.0
        return max(0.0, min(1.0, score))

    @staticmethod
    def _deduplicate_rag_sources(sources: list[ResearchSource]) -> list[ResearchSource]:
        dedup: dict[tuple[str, int], ResearchSource] = {}
        for source in sources:
            key = ((source.document or source.title).lower(), source.page or -1)
            existing = dedup.get(key)
            if existing is None or source.score > existing.score:
                dedup[key] = source
        return list(dedup.values())

    @staticmethod
    def _compute_confidence_overall(facts: list[ResearchFact], sources: list[ResearchSource]) -> float:
        fact_avg = sum(f.confidence for f in facts) / len(facts) if facts else 0.0
        src_avg = sum(s.score for s in sources) / len(sources) if sources else 0.0
        return round((fact_avg * 0.6) + (src_avg * 0.4), 2)
