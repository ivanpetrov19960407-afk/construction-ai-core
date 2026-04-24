"""Pydantic-схемы для структурированного ответа Researcher."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field


class Diagnostic(BaseModel):
    code: str
    message: str
    severity: Literal["info", "warn", "error"]
    component: str = "researcher"
    stage: str | None = None
    source_id: str | None = None
    fact_id: str | None = None

    model_config = ConfigDict(extra="forbid")


class ResearchEvidence(BaseModel):
    source_id: str
    quote: str
    locator: str | None = None
    chunk_id: str | None = None
    document_id: str | None = None
    page: int | None = None
    span_start: int | None = None
    span_end: int | None = None
    support_status: (
        Literal[
            "supported",
            "partially_supported",
            "unsupported",
            "conflicting",
            "quote_found_but_not_entailing",
        ]
        | None
    ) = None
    extraction_method: str | None = None

    model_config = ConfigDict(extra="forbid")


class ResearchFact(BaseModel):
    """Найденный факт и оценка его применимости."""

    text: str
    applicability: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_ids: list[str] = Field(default_factory=list)
    evidence: list[ResearchEvidence] = Field(default_factory=list)
    support_status: (
        Literal[
            "supported",
            "partially_supported",
            "unsupported",
            "conflicting",
            "quote_found_but_not_entailing",
        ]
        | None
    ) = None

    model_config = ConfigDict(extra="forbid")


class ResearchSource(BaseModel):
    """Нормализованный источник (RAG / web / memory)."""

    id: str
    type: str
    title: str
    document: str | None = None
    page: int | None = None
    url: str | None = None
    locator: str | None = None
    snippet: str | None = None
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    published_at: str | None = None
    access_scope: str | None = None

    # Rich metadata (optional, backward-compatible).
    source_id: str | None = None
    source_type: str | None = None
    document_id: str | None = None
    chunk_id: str | None = None
    section: str | None = None
    jurisdiction: str | None = None
    authority: str | None = None
    document_version: str | None = None
    effective_from: str | None = None
    effective_to: str | None = None
    is_active: bool | None = None
    ingested_at: str | None = None
    checksum: str | None = None
    text_hash: str | None = None
    chunk_text: str | None = None
    full_text: str | None = None
    tenant_id: str | None = None
    project_id: str | None = None
    org_id: str | None = None
    user_id: str | None = None
    quality_score: float | None = Field(default=None, ge=0.0, le=1.0)
    retrieval_score: float | None = Field(default=None, ge=0.0, le=1.0)

    model_config = ConfigDict(extra="forbid")

    def to_public_source(self) -> ResearchSource:
        return self.model_copy(
            update={"tenant_id": None, "project_id": None, "org_id": None, "user_id": None}
        )


class ResearchResponse(BaseModel):
    """Структурированный payload ответа Researcher."""

    query: str
    facts: list[ResearchFact] = Field(default_factory=list)
    sources: list[ResearchSource] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)
    diagnostics_struct: list[Diagnostic] | None = None
    confidence_overall: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence_breakdown: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def diagnostics_legacy(self) -> list[str]:
        """Legacy compat aggregated diagnostics list."""
        legacy = list(dict.fromkeys(self.diagnostics or []))
        if self.diagnostics_struct:
            legacy.extend(f"{item.code}:{item.message}" for item in self.diagnostics_struct)
        return list(dict.fromkeys(legacy))
