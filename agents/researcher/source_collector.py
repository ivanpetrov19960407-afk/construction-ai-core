from __future__ import annotations

import asyncio
import json
import math
from collections.abc import Callable
from inspect import signature

from pydantic import ValidationError

try:
    from aiolimiter import AsyncLimiter
except Exception:  # pragma: no cover

    class AsyncLimiter:
        def __init__(self, max_rate: float, time_period: float) -> None:
            _ = (max_rate, time_period)

        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, exc_type, exc, tb) -> None:
            _ = (exc_type, exc, tb)
            return None


from agents.researcher.config import ResearcherConfig
from agents.researcher.domain import choose_primary_sources
from agents.researcher.errors import (
    ResearchAccessError,
    ResearchScopeError,
    ResearchSourceError,
)
from agents.researcher.security import InjectionGuard
from agents.researcher.source_components import (
    CacheKeyBuilder,
    SourceDeduplicator,
    SourceSanitizer,
    SourceTruncator,
    URLValidator,
)
from core.cache import RedisCache
from core.rag_engine import RAGEngine
from core.tools.web_search import WebSearchTool
from schemas.research import Diagnostic, ResearchSource

try:
    from api.metrics import RESEARCHER_INJECTION_DETECTED_TOTAL
except Exception:  # pragma: no cover - metrics optional in tests
    RESEARCHER_INJECTION_DETECTED_TOTAL = None  # type: ignore[assignment]

_REQUIRED_SCOPE_CONTEXT: dict[str, tuple[str, ...]] = {
    "private": ("user_id",),
    "user": ("user_id",),
    "org": ("org_id",),
    "tenant": ("tenant_id",),
    "project": ("project_id", "tenant_id"),
}


class SourceCollector:
    """Collect RAG and web sources with composition-based source processing."""

    def __init__(
        self,
        rag_engine: RAGEngine,
        web_search_tool: WebSearchTool,
        cache: RedisCache | None,
        config: ResearcherConfig,
        injection_guard: InjectionGuard | None = None,
        url_validator: URLValidator | None = None,
        deduplicator: SourceDeduplicator | None = None,
        sanitizer: SourceSanitizer | None = None,
        truncator: SourceTruncator | None = None,
        cache_key_builder: CacheKeyBuilder | None = None,
    ) -> None:
        self._rag_engine = rag_engine
        self._web_search_tool = web_search_tool
        self._cache = cache
        self._config = config
        self._injection_guard = injection_guard or InjectionGuard(config)
        self._url_validator = url_validator or URLValidator()
        self._deduplicator = deduplicator or SourceDeduplicator()
        self._sanitizer = sanitizer or SourceSanitizer()
        self._truncator = truncator or SourceTruncator()
        self._cache_key_builder = cache_key_builder or CacheKeyBuilder()
        self._web_limiter = AsyncLimiter(
            max_rate=config.web_rate_limit_per_second, time_period=1
        )
        self._web_limiter_loop_id: int | None = None

    async def collect(
        self,
        query: str,
        *,
        topic_scope: str | None,
        access_scope: str | None,
        context: str,
        user_id: str | None = None,
        org_id: str | None = None,
        tenant_id: str | None = None,
        project_id: str | None = None,
    ) -> tuple[list[ResearchSource], list[Diagnostic], bool]:
        diagnostics: list[Diagnostic] = []
        self._require_scope_context(
            access_scope,
            user_id=user_id,
            org_id=org_id,
            tenant_id=tenant_id,
            project_id=project_id,
        )
        cache_key = self._build_cache_key(
            query,
            topic_scope,
            access_scope,
            context,
            user_id=user_id,
            org_id=org_id,
            tenant_id=tenant_id,
            project_id=project_id,
        )

        cached_sources = await self._load_from_cache(cache_key, diagnostics)
        if cached_sources is not None:
            return cached_sources, diagnostics, True

        rag_sources = await self._safe_collect_rag(
            query,
            topic_scope,
            access_scope,
            context,
            diagnostics,
            user_id=user_id,
            org_id=org_id,
            tenant_id=tenant_id,
            project_id=project_id,
        )

        web_sources = await self._safe_collect_web_if_needed(
            query, topic_scope, access_scope, rag_sources, diagnostics
        )

        candidate_pool = sorted(
            [*rag_sources, *web_sources], key=lambda s: s.score, reverse=True
        )[: self._config.candidate_pool_size]
        compact_sources = self._truncator.truncate(
            choose_primary_sources(query, candidate_pool)[
                : self._config.final_top_k_sources
            ],
            self._config.max_prompt_chars,
        )
        await self._save_to_cache(cache_key, compact_sources, diagnostics)
        return compact_sources, diagnostics, False

    async def _safe_collect_rag(
        self,
        query: str,
        topic_scope: str | None,
        access_scope: str | None,
        context: str,
        diagnostics: list[Diagnostic],
        *,
        user_id: str | None,
        org_id: str | None,
        tenant_id: str | None,
        project_id: str | None,
    ) -> list[ResearchSource]:
        try:
            rag = await self._collect_rag(
                query,
                topic_scope,
                access_scope,
                context,
                user_id=user_id,
                org_id=org_id,
                tenant_id=tenant_id,
                project_id=project_id,
            )
        except ResearchSourceError:
            raise
        except Exception as exc:  # noqa: BLE001
            diagnostics.append(
                Diagnostic(
                    code="rag_failed",
                    message=type(exc).__name__,
                    severity="error",
                    component="source_collector",
                    stage="collect",
                )
            )
            return []

        sanitized_rag, sanitize_diag = self._sanitize_sources(rag)
        diagnostics.extend(sanitize_diag)
        return self._deduplicator.deduplicate_rag(sanitized_rag)

    async def _safe_collect_web_if_needed(
        self,
        query: str,
        topic_scope: str | None,
        access_scope: str | None,
        rag_sources: list[ResearchSource],
        diagnostics: list[Diagnostic],
    ) -> list[ResearchSource]:
        need_web = self._need_web_fallback(rag_sources)
        effective_scope = (access_scope or "public").strip()
        non_public_scope = effective_scope != "public"
        web_allowed = not non_public_scope or bool(
            self._config.allow_external_web_for_private_scopes
        )
        if not need_web:
            return []
        if non_public_scope and not web_allowed:
            diagnostics.append(
                Diagnostic(
                    code="web_fallback_blocked_private_scope",
                    message="web fallback blocked for non-public scope",
                    severity="warn",
                    component="source_collector",
                    stage="collect",
                )
            )
            return []

        try:
            web = await self._collect_web(query, topic_scope)
        except Exception as exc:  # noqa: BLE001
            diagnostics.append(
                Diagnostic(
                    code="web_failed",
                    message=type(exc).__name__,
                    severity="warn",
                    component="source_collector",
                    stage="collect",
                )
            )
            return []

        sanitized_web, sanitize_diag = self._sanitize_sources(web)
        diagnostics.extend(sanitize_diag)
        diagnostics.append(
            Diagnostic(
                code="web_fallback",
                message="web fallback used",
                severity="info",
                component="source_collector",
                stage="collect",
            )
        )
        return sanitized_web

    async def _load_from_cache(
        self, cache_key: str, diagnostics: list[Diagnostic]
    ) -> list[ResearchSource] | None:
        if self._cache is None:
            return None
        try:
            cached = await self._cache.get(cache_key)
        except Exception:  # noqa: BLE001
            diagnostics.append(
                Diagnostic(
                    code="cache_unavailable",
                    message="cache_unavailable",
                    severity="warn",
                    component="source_collector",
                    stage="collect",
                )
            )
            return None
        if not cached:
            return None
        try:
            items = json.loads(cached)
            parsed = [ResearchSource.model_validate(item) for item in items]
        except (json.JSONDecodeError, ValidationError):
            diagnostics.append(
                Diagnostic(
                    code="cache_parse_failed",
                    message="cache parse failed",
                    severity="warn",
                    component="source_collector",
                    stage="collect",
                )
            )
            return None

        sanitized, sanitize_diag = self._sanitize_sources(parsed)
        diagnostics.extend(sanitize_diag)
        return sanitized

    async def _save_to_cache(
        self,
        cache_key: str,
        sources: list[ResearchSource],
        diagnostics: list[Diagnostic],
    ) -> None:
        if self._cache is None or not sources:
            return
        try:
            await self._cache.set(
                cache_key,
                json.dumps(
                    [source.model_dump() for source in sources], ensure_ascii=False
                ),
                ttl=self._config.cache_ttl_seconds,
            )
        except Exception:  # noqa: BLE001
            diagnostics.append(
                Diagnostic(
                    code="cache_unavailable",
                    message="cache_unavailable",
                    severity="warn",
                    component="source_collector",
                    stage="collect",
                )
            )

    def _build_cache_key(
        self,
        query: str,
        topic_scope: str | None,
        access_scope: str | None,
        context: str,
        *,
        user_id: str | None,
        org_id: str | None,
        tenant_id: str | None,
        project_id: str | None,
    ) -> str:
        return self._cache_key_builder.build(
            query=query,
            topic_scope=topic_scope,
            access_scope=access_scope,
            context=context,
            cache_schema_version=self._config.cache_schema_version,
            cache_embedding_version=self._config.cache_embedding_version,
            security_policy_version=self._config.security_policy_version,
            user_id=user_id,
            org_id=org_id,
            tenant_id=tenant_id,
            project_id=project_id,
        )

    @staticmethod
    def _require_scope_context(
        access_scope: str | None,
        *,
        user_id: str | None,
        org_id: str | None,
        tenant_id: str | None,
        project_id: str | None,
    ) -> None:
        if access_scope is None:
            scope = "public"
        else:
            scope = access_scope.strip().lower()
        if not scope:
            raise ResearchScopeError("empty access_scope is forbidden")
        if scope == "public":
            return
        required = _REQUIRED_SCOPE_CONTEXT.get(scope)
        if required is None:
            raise ResearchScopeError(f"unknown access_scope={access_scope}")
        present = {
            "user_id": bool(user_id),
            "org_id": bool(org_id),
            "tenant_id": bool(tenant_id),
            "project_id": bool(project_id),
        }
        missing = [field for field in required if not present[field]]
        if missing:
            raise ResearchAccessError(
                f"access_scope={scope} requires context fields: {', '.join(missing)}"
            )

    async def _collect_rag(
        self,
        query: str,
        topic_scope: str | None,
        access_scope: str | None,
        context: str,
        *,
        user_id: str | None,
        org_id: str | None,
        tenant_id: str | None,
        project_id: str | None,
    ) -> list[ResearchSource]:
        retrieval_query = "\n".join(
            part for part in [query, topic_scope, context] if part
        ).strip()
        kwargs = {
            "n_results": self._config.candidate_pool_size,
            "filter_scope": access_scope,
            "tenant_id": tenant_id,
            "org_id": org_id,
            "project_id": project_id,
            "user_id": user_id,
        }

        if access_scope and access_scope != "public":
            if not bool(getattr(self._rag_engine, "supports_identity_filters", True)):
                raise ResearchSourceError("rag_identity_filters_unsupported")
            validator = getattr(
                self._rag_engine, "validate_identity_filter_support", None
            )
            if callable(validator):
                validator()

        sig = signature(self._rag_engine.search)
        supports_kwargs = any(
            p.kind.name == "VAR_KEYWORD" for p in sig.parameters.values()
        )
        supported = set(sig.parameters)
        call_kwargs = (
            kwargs
            if supports_kwargs
            else {k: v for k, v in kwargs.items() if k in supported}
        )
        if access_scope and access_scope != "public" and not supports_kwargs:
            missing = {"tenant_id", "org_id", "project_id", "user_id"} - set(
                call_kwargs
            )
            if missing:
                raise ResearchSourceError("rag_identity_filters_unsupported")

        chunks = await asyncio.wait_for(
            self._rag_engine.search(retrieval_query, **call_kwargs),
            timeout=self._config.rag_timeout_seconds,
        )
        self._validate_identity_boundaries(
            chunks or [],
            tenant_id=tenant_id,
            org_id=org_id,
            project_id=project_id,
            user_id=user_id,
        )
        return self._map_rag_chunks(
            chunks or [],
            access_scope,
            tenant_id=tenant_id,
            org_id=org_id,
            project_id=project_id,
            user_id=user_id,
        )

    @staticmethod
    def _validate_identity_boundaries(
        chunks: list[dict],
        *,
        tenant_id: str | None,
        org_id: str | None,
        project_id: str | None,
        user_id: str | None,
    ) -> None:
        if not any((tenant_id, org_id, project_id, user_id)):
            return
        for chunk in chunks:
            if tenant_id and chunk.get("tenant_id") != tenant_id:
                raise ResearchSourceError("rag_identity_filter_violation")
            if org_id and chunk.get("org_id") != org_id:
                raise ResearchSourceError("rag_identity_filter_violation")
            if project_id and chunk.get("project_id") != project_id:
                raise ResearchSourceError("rag_identity_filter_violation")
            if user_id and chunk.get("user_id") != user_id:
                raise ResearchSourceError("rag_identity_filter_violation")

    def _map_rag_chunks(
        self,
        chunks: list[dict],
        access_scope: str | None,
        *,
        tenant_id: str | None,
        org_id: str | None,
        project_id: str | None,
        user_id: str | None,
    ) -> list[ResearchSource]:
        sources: list[ResearchSource] = []
        for idx, chunk in enumerate(chunks):
            page = int(chunk.get("page", 0) or 0)
            snippet = str(chunk.get("text", ""))[: self._config.snippet_max_chars]
            source_name = str(chunk.get("source", "unknown"))
            score = self._normalize_score(float(chunk.get("score", 0.0) or 0.0))
            sources.append(
                ResearchSource(
                    id=f"rag-{idx}",
                    type="rag",
                    title=source_name,
                    document=source_name,
                    page=page if page > 0 else None,
                    locator=f"стр. {page}" if page > 0 else None,
                    snippet=snippet,
                    chunk_text=str(
                        chunk.get("chunk_text", chunk.get("text", "")) or ""
                    ),
                    score=score,
                    retrieval_score=score,
                    access_scope=access_scope,
                    tenant_id=chunk.get("tenant_id", tenant_id),
                    org_id=chunk.get("org_id", org_id),
                    project_id=chunk.get("project_id", project_id),
                    user_id=chunk.get("user_id", user_id),
                    source_type=chunk.get("source_type"),
                    document_id=chunk.get("document_id"),
                    chunk_id=chunk.get("chunk_id"),
                    section=chunk.get("section"),
                    jurisdiction=chunk.get("jurisdiction"),
                    authority=chunk.get("authority"),
                    document_version=chunk.get("document_version"),
                    effective_from=chunk.get("effective_from"),
                    effective_to=chunk.get("effective_to"),
                    is_active=chunk.get("is_active"),
                    ingested_at=chunk.get("ingested_at"),
                    checksum=chunk.get("checksum"),
                    text_hash=chunk.get("text_hash"),
                    quality_score=chunk.get("quality_score"),
                )
            )
        return sources

    async def _collect_web(
        self, query: str, topic_scope: str | None
    ) -> list[ResearchSource]:
        web_query = "\n".join(part for part in [query, topic_scope] if part)
        self._refresh_web_limiter_if_needed()
        async with self._web_limiter:
            items = await asyncio.wait_for(
                self._web_search_tool.run(
                    web_query, max_results=self._config.candidate_pool_size
                ),
                timeout=self._config.web_timeout_seconds,
            )

        return [
            ResearchSource(
                id=f"web-{idx}",
                type="web",
                title=str(item.get("title", "Web source")),
                url=url,
                snippet=str(item.get("snippet", ""))[: self._config.snippet_max_chars],
                score=self._normalize_score(float(item.get("score", 0.0) or 0.0)),
                retrieval_score=self._normalize_score(
                    float(item.get("score", 0.0) or 0.0)
                ),
                published_at=str(item.get("published_at", "") or "") or None,
            )
            for idx, item in enumerate(items or [])
            if (url := str(item.get("url", "") or ""))
            and self._url_validator.is_allowed(url)
        ]

    def _refresh_web_limiter_if_needed(self) -> None:
        loop_id = id(asyncio.get_running_loop())
        if self._web_limiter_loop_id is None:
            self._web_limiter_loop_id = loop_id
        elif self._web_limiter_loop_id != loop_id:
            self._web_limiter = AsyncLimiter(
                max_rate=self._config.web_rate_limit_per_second, time_period=1
            )
            self._web_limiter_loop_id = loop_id

    def _sanitize_sources(
        self, sources: list[ResearchSource]
    ) -> tuple[list[ResearchSource], list[Diagnostic]]:
        sanitized: list[ResearchSource] = []
        diagnostics: list[Diagnostic] = []
        redacted_count = 0
        sanitize_fn: Callable[[str], tuple[str, bool]] = InjectionGuard.sanitize_snippet
        for source in sources:
            clean_source, flagged = self._sanitizer.sanitize(source, sanitize_fn)
            sanitized.append(clean_source)
            if not flagged:
                continue
            redacted_count += 1
            diagnostics.append(
                Diagnostic(
                    code="prompt_injection_detected",
                    message=f"Textual fields from {source.id} redacted",
                    severity="warn",
                    component="security",
                    stage="sanitize",
                    source_id=source.id,
                )
            )
        if redacted_count and RESEARCHER_INJECTION_DETECTED_TOTAL is not None:
            RESEARCHER_INJECTION_DETECTED_TOTAL.inc(redacted_count)
        return sanitized, diagnostics

    def _need_web_fallback(self, rag_sources: list[ResearchSource]) -> bool:
        if len(rag_sources) < self._config.web_min_rag_sources:
            return True
        avg_score = sum(s.score for s in rag_sources) / max(len(rag_sources), 1)
        info_density = sum(len((s.snippet or "").split()) for s in rag_sources) / max(
            len(rag_sources), 1
        )
        composite = avg_score * math.log(len(rag_sources) + 1) * (info_density / 100.0)
        return composite < self._config.web_min_avg_score

    def _cache_key(
        self,
        query: str,
        topic_scope: str | None,
        access_scope: str | None,
        context: str,
        *,
        user_id: str | None = None,
        org_id: str | None = None,
        tenant_id: str | None = None,
        project_id: str | None = None,
    ) -> str:
        return self._build_cache_key(
            query,
            topic_scope,
            access_scope,
            context,
            user_id=user_id,
            org_id=org_id,
            tenant_id=tenant_id,
            project_id=project_id,
        )

    @staticmethod
    def _is_allowed_url(url: str) -> bool:
        return URLValidator.is_allowed(url)

    @staticmethod
    def _normalize_score(score: float) -> float:
        return min(1.0, max(0.0, score if score <= 1 else score / 100.0))
