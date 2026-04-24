from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
import socket
from ipaddress import ip_address
from urllib.parse import urlparse

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
from agents.researcher.errors import ResearchAccessError, ResearchSourceError
from agents.researcher.security import InjectionGuard
from core.cache import RedisCache
from core.rag_engine import RAGEngine
from core.tools.web_search import WebSearchTool
from schemas.research import Diagnostic, ResearchSource

try:
    from api.metrics import RESEARCHER_INJECTION_DETECTED_TOTAL
except Exception:  # pragma: no cover - metrics optional in tests
    RESEARCHER_INJECTION_DETECTED_TOTAL = None  # type: ignore[assignment]

_WHITESPACE_RE = re.compile(r"\s+")
_SUSPICIOUS_HOST_RE = re.compile(r"(?i)(localhost|\.local$|internal|\.internal$)")

_REQUIRED_SCOPE_CONTEXT: dict[str, tuple[str, ...]] = {
    "private": ("user_id",),
    "user": ("user_id",),
    "org": ("org_id",),
    "tenant": ("tenant_id",),
    "project": ("project_id", "tenant_id"),
}


class SourceCollector:
    """Collect RAG and web sources with dedup, sanitization and cache."""

    def __init__(
        self,
        rag_engine: RAGEngine,
        web_search_tool: WebSearchTool,
        cache: RedisCache | None,
        config: ResearcherConfig,
        injection_guard: InjectionGuard | None = None,
    ) -> None:
        self._rag_engine = rag_engine
        self._web_search_tool = web_search_tool
        self._cache = cache
        self._config = config
        self._injection_guard = injection_guard or InjectionGuard(config)
        self._web_limiter = AsyncLimiter(max_rate=config.web_rate_limit_per_second, time_period=1)
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
        cache_key = self._cache_key(
            query,
            topic_scope,
            access_scope,
            context,
            user_id=user_id,
            org_id=org_id,
            tenant_id=tenant_id,
            project_id=project_id,
        )
        if self._cache is not None:
            try:
                cached = await self._cache.get(cache_key)
            except Exception:  # noqa: BLE001
                cached = None
                diagnostics.append(
                    Diagnostic(
                        code="cache_unavailable",
                        message="cache_unavailable",
                        severity="warn",
                        component="source_collector",
                        stage="collect",
                    )
                )
            if cached:
                try:
                    items = json.loads(cached)
                    sanitized_sources, cached_sec_diag = self._sanitize_sources(
                        [ResearchSource.model_validate(i) for i in items]
                    )
                    diagnostics.extend(cached_sec_diag)
                    return sanitized_sources, diagnostics, True
                except (TypeError, ValueError, json.JSONDecodeError):
                    diagnostics.append(
                        Diagnostic(
                            code="cache_parse_failed",
                            message="cache parse failed",
                            severity="warn",
                            component="source_collector",
                            stage="collect",
                        )
                    )

        rag_task = asyncio.create_task(
            self._collect_rag(
                query,
                topic_scope,
                access_scope,
                context,
                user_id=user_id,
                org_id=org_id,
                tenant_id=tenant_id,
                project_id=project_id,
            )
        )
        web_task = asyncio.create_task(
            self._collect_web_deferred(query, topic_scope, delay_seconds=0.05)
        )

        try:
            rag_result: list[ResearchSource] | Exception = await rag_task
        except Exception as exc:  # noqa: BLE001
            rag_result = exc

        rag_sanitization_diag: list[Diagnostic] = []
        if isinstance(rag_result, Exception):
            if isinstance(rag_result, ResearchSourceError):
                raise rag_result
            diagnostics.append(
                Diagnostic(
                    code="rag_failed",
                    message=type(rag_result).__name__,
                    severity="error",
                    component="source_collector",
                    stage="collect",
                )
            )
            rag_sources: list[ResearchSource] = []
        else:
            sanitized_rag, rag_sanitization_diag = self._sanitize_sources(rag_result)
            rag_sources = self._deduplicate_rag_sources(sanitized_rag)

        need_web = self._need_web_fallback(rag_sources)
        if not need_web:
            web_task.cancel()
            web_result: list[ResearchSource] | Exception = []
        else:
            try:
                web_result = await web_task
            except Exception as exc:  # noqa: BLE001
                web_result = exc

        web_sources: list[ResearchSource] = []
        web_sanitization_diag: list[Diagnostic] = []
        if isinstance(web_result, Exception):
            diagnostics.append(
                Diagnostic(
                    code="web_failed",
                    message=type(web_result).__name__,
                    severity="warn",
                    component="source_collector",
                    stage="collect",
                )
            )
        elif need_web:
            sanitized_web, web_sanitization_diag = self._sanitize_sources(web_result)
            web_sources = sanitized_web
            diagnostics.append(
                Diagnostic(
                    code="web_fallback",
                    message="web fallback used",
                    severity="info",
                    component="source_collector",
                    stage="collect",
                )
            )

        diagnostics.extend(rag_sanitization_diag)
        diagnostics.extend(web_sanitization_diag)

        top_sources = sorted([*rag_sources, *web_sources], key=lambda s: s.score, reverse=True)[
            : self._config.top_k_sources
        ]
        compact_sources = self._truncate_sources(top_sources)

        if compact_sources and self._cache is not None:
            try:
                await self._cache.set(
                    cache_key,
                    json.dumps(
                        [source.model_dump() for source in compact_sources], ensure_ascii=False
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

        return compact_sources, diagnostics, False

    @staticmethod
    def _require_scope_context(
        access_scope: str | None,
        *,
        user_id: str | None,
        org_id: str | None,
        tenant_id: str | None,
        project_id: str | None,
    ) -> None:
        if not access_scope or access_scope == "public":
            return
        required = _REQUIRED_SCOPE_CONTEXT.get(access_scope, ("tenant_id",))
        present = {
            "user_id": bool(user_id),
            "org_id": bool(org_id),
            "tenant_id": bool(tenant_id),
            "project_id": bool(project_id),
        }
        missing = [field for field in required if not present[field]]
        if missing:
            raise ResearchAccessError(
                f"access_scope={access_scope} requires context fields: {', '.join(missing)}"
            )

    async def _collect_web_deferred(
        self, query: str, topic_scope: str | None, delay_seconds: float
    ) -> list[ResearchSource]:
        await asyncio.sleep(delay_seconds)
        return await self._collect_web(query, topic_scope)

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
        retrieval_query = "\n".join(part for part in [query, topic_scope, context] if part).strip()
        kwargs = {
            "n_results": self._config.top_k_sources,
            "filter_scope": access_scope,
            "tenant_id": tenant_id,
            "org_id": org_id,
            "project_id": project_id,
            "user_id": user_id,
        }
        try:
            coro = self._rag_engine.search(retrieval_query, **kwargs)
        except TypeError:
            if access_scope and access_scope != "public":
                raise ResearchSourceError(
                    "RAG engine does not support identity filters for non-public scope"
                )
            fallback = {k: v for k, v in kwargs.items() if k in {"n_results", "filter_scope"}}
            coro = self._rag_engine.search(retrieval_query, **fallback)
        chunks = await asyncio.wait_for(coro, timeout=self._config.rag_timeout_seconds)

        sources: list[ResearchSource] = []
        for idx, chunk in enumerate(chunks or []):
            page = int(chunk.get("page", 0) or 0)
            snippet = str(chunk.get("text", ""))[: self._config.snippet_max_chars]
            source_name = str(chunk.get("source", "unknown"))
            normalized_score = self._normalize_score(float(chunk.get("score", 0.0) or 0.0))
            sources.append(
                ResearchSource(
                    id=f"rag-{idx}",
                    type="rag",
                    title=source_name,
                    document=source_name,
                    page=page if page > 0 else None,
                    locator=f"стр. {page}" if page > 0 else None,
                    snippet=snippet,
                    score=normalized_score,
                    retrieval_score=normalized_score,
                    access_scope=access_scope,
                    tenant_id=tenant_id,
                    org_id=org_id,
                    project_id=project_id,
                    user_id=user_id,
                    document_id=chunk.get("document_id"),
                    chunk_id=chunk.get("chunk_id"),
                    section=chunk.get("section"),
                    jurisdiction=chunk.get("jurisdiction"),
                    authority=chunk.get("authority"),
                    document_version=chunk.get("document_version"),
                    effective_from=chunk.get("effective_from"),
                    effective_to=chunk.get("effective_to"),
                    is_active=chunk.get("is_active"),
                    quality_score=chunk.get("quality_score"),
                )
            )
        return sources

    async def _collect_web(self, query: str, topic_scope: str | None) -> list[ResearchSource]:
        web_query = "\n".join(part for part in [query, topic_scope] if part)
        loop_id = id(asyncio.get_running_loop())
        if self._web_limiter_loop_id is None:
            self._web_limiter_loop_id = loop_id
        elif self._web_limiter_loop_id != loop_id:
            self._web_limiter = AsyncLimiter(
                max_rate=self._config.web_rate_limit_per_second, time_period=1
            )
            self._web_limiter_loop_id = loop_id
        async with self._web_limiter:
            items = await asyncio.wait_for(
                self._web_search_tool.run(web_query, max_results=self._config.top_k_sources),
                timeout=self._config.web_timeout_seconds,
            )
        sources: list[ResearchSource] = []
        for idx, item in enumerate(items or []):
            url = str(item.get("url", "") or "")
            if not self._is_allowed_url(url):
                continue
            snippet = str(item.get("snippet", ""))[: self._config.snippet_max_chars]
            score = self._normalize_score(float(item.get("score", 0.0) or 0.0))
            sources.append(
                ResearchSource(
                    id=f"web-{idx}",
                    type="web",
                    title=str(item.get("title", "Web source")),
                    url=url,
                    snippet=snippet,
                    score=score,
                    retrieval_score=score,
                    published_at=str(item.get("published_at", "") or "") or None,
                )
            )
        return sources

    def _need_web_fallback(self, rag_sources: list[ResearchSource]) -> bool:
        if len(rag_sources) < self._config.web_min_rag_sources:
            return True
        avg_score = sum(s.score for s in rag_sources) / max(len(rag_sources), 1)
        info_density = sum(len((s.snippet or "").split()) for s in rag_sources) / max(
            len(rag_sources), 1
        )
        composite = avg_score * math.log(len(rag_sources) + 1) * (info_density / 100.0)
        return composite < self._config.web_min_avg_score

    @staticmethod
    def _normalize_score(score: float) -> float:
        return min(1.0, max(0.0, score if score <= 1 else score / 100.0))

    def _deduplicate_rag_sources(self, sources: list[ResearchSource]) -> list[ResearchSource]:
        dedup: dict[tuple[str, int, str], ResearchSource] = {}
        for source in sources:
            text_hash = hashlib.sha256((source.snippet or "").encode()).hexdigest()[:12]
            key = ((source.document or "").lower(), source.page or -1, text_hash)
            existing = dedup.get(key)
            if existing is None or source.score > existing.score:
                dedup[key] = source
        return list(dedup.values())

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
        norm_query = _WHITESPACE_RE.sub(" ", query).strip().lower()
        query_hash = hashlib.sha256(f"{norm_query}|{context}".encode()).hexdigest()[:16]
        scope_hash = hashlib.sha256(
            f"{topic_scope or ''}|{access_scope or ''}".encode()
        ).hexdigest()[:12]
        identity = "|".join(
            [
                f"user:{user_id or ''}",
                f"org:{org_id or ''}",
                f"tenant:{tenant_id or ''}",
                f"project:{project_id or ''}",
            ]
        )
        identity_hash = hashlib.sha256(identity.encode()).hexdigest()[:12]
        return (
            f"research:{self._config.cache_schema_version}:{self._config.cache_embedding_version}:"
            f"{self._config.security_policy_version}:{query_hash}:{scope_hash}:{identity_hash}"
        )

    @staticmethod
    def _is_allowed_url(url: str) -> bool:
        if not url:
            return False
        try:
            parsed = urlparse(url)
        except ValueError:
            return False
        if parsed.scheme not in {"http", "https"}:
            return False
        host = (parsed.hostname or "").strip().rstrip(".")
        if not host or _SUSPICIOUS_HOST_RE.search(host):
            return False
        try:
            host = host.encode("idna").decode("ascii")
        except UnicodeError:
            return False

        if host == "localhost":
            return False

        try:
            ip = ip_address(host)
            return not (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
            )
        except ValueError:
            pass

        try:
            infos = socket.getaddrinfo(host, parsed.port or 443, proto=socket.IPPROTO_TCP)
        except socket.gaierror:
            return True
        for info in infos:
            resolved_ip = ip_address(info[4][0])
            if (
                resolved_ip.is_private
                or resolved_ip.is_loopback
                or resolved_ip.is_link_local
                or resolved_ip.is_reserved
                or resolved_ip.is_multicast
            ):
                return False
        return True

    def _sanitize_sources(
        self, sources: list[ResearchSource]
    ) -> tuple[list[ResearchSource], list[Diagnostic]]:
        sanitized: list[ResearchSource] = []
        diagnostics: list[Diagnostic] = []
        redacted_count = 0
        for source in sources:
            clean_snippet, was_redacted = InjectionGuard.sanitize_snippet(source.snippet or "")
            if was_redacted:
                redacted_count += 1
                diagnostics.append(
                    Diagnostic(
                        code="prompt_injection_detected",
                        message=f"Snippet from {source.id} redacted",
                        severity="warn",
                        component="security",
                        stage="sanitize",
                        source_id=source.id,
                    )
                )
            sanitized.append(source.model_copy(update={"snippet": clean_snippet}))
        if redacted_count and RESEARCHER_INJECTION_DETECTED_TOTAL is not None:
            try:
                RESEARCHER_INJECTION_DETECTED_TOTAL.inc(redacted_count)
            except Exception:
                pass
        return sanitized, diagnostics

    def _truncate_sources(self, sources: list[ResearchSource]) -> list[ResearchSource]:
        total_chars = sum(len(s.snippet or "") for s in sources)
        if total_chars <= self._config.max_prompt_chars:
            return sources
        ratio = self._config.max_prompt_chars / max(total_chars, 1)
        truncated: list[ResearchSource] = []
        for source in sources:
            snippet = source.snippet or ""
            new_len = max(50, int(len(snippet) * ratio))
            truncated.append(source.model_copy(update={"snippet": snippet[:new_len]}))
        return truncated
