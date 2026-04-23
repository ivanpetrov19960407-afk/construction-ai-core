from __future__ import annotations

import re
import unicodedata
from typing import Any

_ZERO_WIDTH_RE = re.compile(r"[\u200B-\u200F\uFEFF]")
_WHITESPACE_RE = re.compile(r"\s+")
_EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\s\-()]{0,3}){7,15}\d")


class InjectionGuard:
    """Detects and redacts suspicious prompt-injection fragments."""

    _category_patterns: tuple[re.Pattern[str], ...] = (
        re.compile(
            r"(?i)\b(ignore|disregard|forget|override)\b.*\b(previous|prior|above|system)\b.*"
            r"\b(instruction|prompt|rule)s?\b"
        ),
        re.compile(
            r"(?i)\b(игнорируй|забудь|отмени|пренебреги|переопредели)\b.*"
            r"\b(предыдущ|ранн|выше|системн)\w*\b.*\b(инструкц|промпт|правил)\w*\b"
        ),
        re.compile(r"(?i)(^|\s)(system:|assistant:|developer:|user:)"),
        re.compile(r"<\|im_start\|>", re.IGNORECASE),
    )

    def __init__(self, config: Any | None = None) -> None:
        self._config = config

    @classmethod
    def normalize(cls, text: str) -> str:
        normalized = unicodedata.normalize("NFKC", text)
        normalized = _ZERO_WIDTH_RE.sub("", normalized)
        return _WHITESPACE_RE.sub(" ", normalized).strip()

    @classmethod
    def sanitize_snippet(cls, snippet: str) -> tuple[str, bool]:
        normalized = cls.normalize(snippet)
        if not normalized:
            return "", False
        if cls.is_suspicious(normalized):
            return "[REDACTED: suspected prompt injection]", True
        return normalized, False

    @classmethod
    def is_suspicious(cls, text: str) -> bool:
        normalized = cls.normalize(text)
        return any(pattern.search(normalized) for pattern in cls._category_patterns)

    def contains_prompt_injection(self, text: str) -> bool:
        """Public API: whether snippet looks like a prompt-injection attempt."""
        return self.is_suspicious(text)

    def _contains_prompt_injection(self, text: str) -> bool:  # pragma: no cover - legacy alias
        """Deprecated alias kept for backward compatibility."""
        return self.contains_prompt_injection(text)

    def mask_pii(self, text: str, limit: int = 200) -> str:
        return sanitize_pii(text, limit=limit)


def sanitize_pii(text: str, limit: int = 200) -> str:
    """Trim + mask lightweight PII for safe logging."""

    clipped = text[:limit]
    clipped = _EMAIL_RE.sub("[email]", clipped)
    clipped = _PHONE_RE.sub("[phone]", clipped)
    return clipped
