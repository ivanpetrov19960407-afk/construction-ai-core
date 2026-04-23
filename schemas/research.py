"""Pydantic-схемы для структурированного ответа Researcher."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ResearchFact(BaseModel):
    """Найденный факт и оценка его применимости."""

    text: str
    applicability: str = ""
    confidence: float = Field(ge=0.0, le=1.0)
    source_ids: list[str] = Field(default_factory=list)


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


class ResearchResponse(BaseModel):
    """Структурированный payload ответа Researcher."""

    query: str
    facts: list[ResearchFact] = Field(default_factory=list)
    sources: list[ResearchSource] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)
    confidence_overall: float = Field(default=0.0, ge=0.0, le=1.0)
