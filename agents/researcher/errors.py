from __future__ import annotations

from typing import Any


class ResearchError(Exception):
    """Base exception for researcher pipeline."""


class ResearchAccessError(ResearchError):
    """Access context is missing or invalid for requested scope."""


class ResearchScopeError(ResearchAccessError):
    """Unknown or unsupported access scope."""


class ResearchSourceError(ResearchError):
    """Source collection failed or produced unsafe/invalid state."""


class ResearchLLMError(ResearchError):
    """Structured LLM response failed (timeout, schema, malformed JSON, etc)."""

    def __init__(self, code: str, message: str | None = None, *, details: dict[str, Any] | None = None):
        self.code = code
        self.details = details or {}
        super().__init__(message or code)


class ResearchValidationError(ResearchError):
    """Fact/evidence validation failed."""

    def __init__(self, code: str, message: str | None = None, *, details: dict[str, Any] | None = None):
        self.code = code
        self.details = details or {}
        super().__init__(message or code)
