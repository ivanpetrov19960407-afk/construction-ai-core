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
    candidate_pool_size: int = 20
    final_top_k_sources: int = 5
    allow_external_web_for_private_scopes: bool = False
    allow_fenced_json_output: bool = False
    max_prompt_chars: int = 12000
    prompt_system_budget_chars: int = 1200
    prompt_query_budget_chars: int = 2000
    prompt_context_budget_chars: int = 1800
    prompt_sources_budget_chars: int = 6500
    prompt_per_source_budget_chars: int = 750

    # Deprecated legacy confidence knobs kept for compatibility.
    confidence_weight_fact: float = 0.6
    confidence_weight_source: float = 0.4

    # Evidence/support scoring weights.
    support_weight_evidence_coverage: float = 0.35
    support_weight_source_quality: float = 0.2
    support_weight_independent_sources: float = 0.2
    support_weight_recency: float = 0.15
    support_weight_conflict_penalty: float = 0.1

    cache_ttl_seconds: int = 3600
    cache_schema_version: str = "v4"
    cache_embedding_version: str = "v1"
    security_policy_version: str = "sec-v2"
    retry_attempts: int = 3
    retry_initial_delay: float = 0.5
    llm_reask_limit: int = 1
    fact_citation_min_similarity: float = 0.6
    web_rate_limit_per_second: float = 1.0


__all__ = ["ResearcherConfig"]
