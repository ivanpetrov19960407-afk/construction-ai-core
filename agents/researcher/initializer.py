from __future__ import annotations

from dataclasses import dataclass

from agents.researcher.config import ResearcherConfig
from agents.researcher.llm_client import StructuredLLMClient
from agents.researcher.security import InjectionGuard
from agents.researcher.source_collector import SourceCollector
from config.settings import settings
from core.cache import RedisCache
from core.llm_router import LLMRouter
from core.rag_engine import RAGEngine
from core.tools.web_search import WebSearchTool


@dataclass
class ResearcherComponents:
    collector: SourceCollector
    llm_client: StructuredLLMClient
    cache: RedisCache | None


class ResearcherInitializer:
    @staticmethod
    def initialize(
        *,
        llm_router: LLMRouter,
        config: ResearcherConfig,
        rag_engine: RAGEngine | None,
        web_search_tool: WebSearchTool | None,
        cache: RedisCache | None,
    ) -> ResearcherComponents:
        config.rag_timeout_seconds = float(
            getattr(settings, "research_rag_timeout_seconds", config.rag_timeout_seconds)
        )
        config.web_timeout_seconds = float(
            getattr(settings, "research_web_timeout_seconds", config.web_timeout_seconds)
        )
        config.llm_timeout_seconds = float(
            getattr(settings, "research_llm_timeout_seconds", config.llm_timeout_seconds)
        )

        resolved_cache = cache
        if resolved_cache is None:
            try:
                resolved_cache = RedisCache(settings.redis_url)
            except Exception:
                resolved_cache = None

        collector = SourceCollector(
            rag_engine or RAGEngine(),
            web_search_tool or WebSearchTool(),
            resolved_cache,
            config,
            injection_guard=InjectionGuard(config),
        )
        return ResearcherComponents(
            collector=collector,
            llm_client=StructuredLLMClient(llm_router, config),
            cache=resolved_cache,
        )
