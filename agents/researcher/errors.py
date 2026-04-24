from __future__ import annotations


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


class ResearchValidationError(ResearchError):
    """Fact/evidence validation failed."""
