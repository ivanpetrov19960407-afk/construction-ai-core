"""Pydantic-схемы для структурированного ответа Researcher."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, computed_field


class Diagnostic(BaseModel):
    code: str
    message: str
    severity: Literal["info", "warn", "error"]
    stage: str


class ResearchEvidence(BaseModel):
    source_id: str
    quote: str
    locator: str | None = None


class ResearchFact(BaseModel):
    """Найденный факт и оценка его применимости."""

    text: str
    applicability: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_ids: list[str] = Field(default_factory=list)
    evidence: list[ResearchEvidence] = Field(default_factory=list)


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

    @computed_field  # type: ignore[prop-decorator]
    @property
    def diagnostics_legacy(self) -> list[str]:
        """Legacy compat aggregated diagnostics list."""
        legacy = list(dict.fromkeys(self.diagnostics or []))
        if self.diagnostics_struct:
            legacy.extend(f"{item.code}:{item.message}" for item in self.diagnostics_struct)
        return list(dict.fromkeys(legacy))
