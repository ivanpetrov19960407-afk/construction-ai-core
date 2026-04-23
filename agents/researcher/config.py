from __future__ import annotations

from pydantic_settings import BaseSettings


class ResearcherConfig(BaseSettings):
    """Runtime settings for ResearcherAgent internals."""

    llm_timeout_seconds: float = 45.0
    rag_timeout_seconds: float = 12.0
    web_timeout_seconds: float = 12.0
    web_min_rag_sources: int = 2
    web_min_avg_score: float = 0.35
    web_min_snippet_chars: int = 500
    snippet_max_chars: int = 400
    top_k_sources: int = 5
    max_prompt_chars: int = 12000
    confidence_weight_fact: float = 0.6
    confidence_weight_source: float = 0.4
    cache_ttl_seconds: int = 3600
    cache_schema_version: str = "v3"
    cache_embedding_version: str = "v1"
    retry_attempts: int = 3
    retry_initial_delay: float = 0.5
    fact_citation_min_similarity: float = 0.6
    web_rate_limit_per_second: float = 1.0


__all__ = ["ResearcherConfig"]
