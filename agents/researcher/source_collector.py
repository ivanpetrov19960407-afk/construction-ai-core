from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
from ipaddress import ip_address
from typing import Any
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

    async def collect(
        self,
        query: str,
        *,
        topic_scope: str | None,
        access_scope: str | None,
        context: str,
        user_id: str | None = None,
    ) -> tuple[list[ResearchSource], list[Diagnostic], bool]:
        """Collect, sanitize and rank sources.

        Returns: (sources, diagnostics, cache_hit).
        Sanitization of snippets happens before caching, dedup and return,
        so no raw untrusted content leaves this method.
        """
        diagnostics: list[Diagnostic] = []
        _ = user_id
        cache_key = self._cache_key(query, topic_scope, access_scope, context)
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
                        stage="collect",
                    )
                )
            if cached:
                try:
                    items = json.loads(cached)
                    # Cached sources are already sanitized (see below).
                    return (
                        [ResearchSource.model_validate(i) for i in items],
                        diagnostics,
                        True,
                    )
                except (TypeError, ValueError, json.JSONDecodeError):
                    diagnostics.append(
                        Diagnostic(
                            code="cache_parse_failed",
                            message="cache parse failed",
                            severity="warn",
                            stage="collect",
                        )
                    )

        rag_task = asyncio.create_task(self._collect_rag(query, topic_scope, access_scope, context))
        web_task = asyncio.create_task(self._collect_web_deferred(query, topic_scope, delay_seconds=0.05))
        rag_result: list[ResearchSource] | Exception
        try:
            rag_result = await rag_task
        except Exception as exc:  # noqa: BLE001
            rag_result = exc

        # IMPORTANT: sanitize RAG snippets BEFORE the fallback decision.
        # Otherwise a prompt-injection chunk with inflated word count could
        # artificially raise info_density in _need_web_fallback and suppress
        # a legitimate web fallback, leaving us with low-information redacted
        # snippets at the end.
        rag_sanitization_diag: list[Diagnostic] = []
        if isinstance(rag_result, Exception):
            diagnostics.append(
                Diagnostic(
                    code="rag_failed",
                    message=type(rag_result).__name__,
                    severity="error",
                    stage="collect",
                )
            )
            rag_sources: list[ResearchSource] = []
        else:
            sanitized_rag, rag_sanitization_diag = self._sanitize_sources(rag_result)
            rag_sources = self._deduplicate_rag_sources(sanitized_rag)

        # Fallback decision uses post-sanitization snippets.
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
                    stage="collect",
                )
            )

        diagnostics.extend(rag_sanitization_diag)
        diagnostics.extend(web_sanitization_diag)

        top_sources = sorted(
            [*rag_sources, *web_sources], key=lambda s: s.score, reverse=True
        )[: self._config.top_k_sources]
        compact_sources = self._truncate_sources(top_sources)

        if compact_sources and self._cache is not None:
            try:
                await self._cache.set(
                    cache_key,
                    json.dumps([source.model_dump() for source in compact_sources], ensure_ascii=False),
                    ttl=self._config.cache_ttl_seconds,
                )
            except Exception:  # noqa: BLE001
                diagnostics.append(
                    Diagnostic(
                        code="cache_unavailable",
                        message="cache_unavailable",
                        severity="warn",
                        stage="collect",
                    )
                )

        return compact_sources, diagnostics, False

    async def _collect_web_deferred(
        self, query: str, topic_scope: str | None, delay_seconds: float
    ) -> list[ResearchSource]:
        await asyncio.sleep(delay_seconds)
        return await self._collect_web(query, topic_scope)

    async def _collect_rag(
        self, query: str, topic_scope: str | None, access_scope: str | None, context: str
    ) -> list[ResearchSource]:
        retrieval_query = "\n".join(part for part in [query, topic_scope, context] if part).strip()
        chunks = await asyncio.wait_for(
            self._rag_engine.search(
                retrieval_query,
                n_results=self._config.top_k_sources,
                filter_scope=access_scope,
            ),
            timeout=self._config.rag_timeout_seconds,
        )
        sources: list[ResearchSource] = []
        for idx, chunk in enumerate(chunks or []):
            page = int(chunk.get("page", 0) or 0)
            # Raw snippet; central sanitization happens later in _sanitize_sources.
            snippet = str(chunk.get("text", ""))[: self._config.snippet_max_chars]
            source_name = str(chunk.get("source", "unknown"))
            sources.append(
                ResearchSource(
                    id=f"rag-{idx}",
                    type="rag",
                    title=source_name,
                    document=source_name,
                    page=page if page > 0 else None,
                    locator=f"стр. {page}" if page > 0 else None,
                    snippet=snippet,
                    score=self._normalize_score(float(chunk.get("score", 0.0) or 0.0)),
                    access_scope=access_scope,
                )
            )
        return sources

    async def _collect_web(self, query: str, topic_scope: str | None) -> list[ResearchSource]:
        web_query = "\n".join(part for part in [query, topic_scope] if part)
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
            # Raw snippet; central sanitization happens later in _sanitize_sources.
            snippet = str(item.get("snippet", ""))[: self._config.snippet_max_chars]
            sources.append(
                ResearchSource(
                    id=f"web-{idx}",
                    type="web",
                    title=str(item.get("title", "Web source")),
                    url=url,
                    snippet=snippet,
                    score=self._normalize_score(float(item.get("score", 0.0) or 0.0)),
                    published_at=str(item.get("published_at", "") or "") or None,
                )
            )
        return sources

    def _need_web_fallback(self, rag_sources: list[ResearchSource]) -> bool:
        if len(rag_sources) < self._config.web_min_rag_sources:
            return True
        avg_score = sum(s.score for s in rag_sources) / max(len(rag_sources), 1)
        info_density = sum(len((s.snippet or "").split()) for s in rag_sources) / max(len(rag_sources), 1)
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

    def _cache_key(self, query: str, topic_scope: str | None, access_scope: str | None, context: str) -> str:
        norm_query = _WHITESPACE_RE.sub(" ", query).strip().lower()
        query_hash = hashlib.sha256(f"{norm_query}|{context}".encode()).hexdigest()[:16]
        scope_hash = hashlib.sha256(f"{topic_scope or ''}|{access_scope or ''}".encode()).hexdigest()[:12]
        return (
            f"research:{self._config.cache_schema_version}:{self._config.cache_embedding_version}:"
            f"{query_hash}:{scope_hash}"
        )

    @staticmethod
    def _is_allowed_url(url: str) -> bool:
        if not url:
            return False
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return False
        host = parsed.hostname or ""
        try:
            ip = ip_address(host)
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return False
        except ValueError:
            pass
        return True

    def _sanitize_sources(
        self, sources: list[ResearchSource]
    ) -> tuple[list[ResearchSource], list[Diagnostic]]:
        """Strip prompt-injection payloads from snippets before they reach LLM/cache."""
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
                        stage="security",
                    )
                )
            sanitized.append(source.model_copy(update={"snippet": clean_snippet}))
        if redacted_count and RESEARCHER_INJECTION_DETECTED_TOTAL is not None:
            try:
                RESEARCHER_INJECTION_DETECTED_TOTAL.inc(redacted_count)
            except Exception:  # noqa: BLE001 - metrics must never break pipeline
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
