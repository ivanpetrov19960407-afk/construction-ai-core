from __future__ import annotations

import base64
import binascii
import re
import unicodedata
from typing import Any

_ZERO_WIDTH_RE = re.compile(r"[\u200B-\u200F\u2060\uFEFF]")
_WHITESPACE_RE = re.compile(r"\s+")
_EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\s\-()]{0,3}){7,15}\d")
_MARKDOWN_HIDDEN_RE = re.compile(r"\[[^\]]+\]\([^\)]*\)")
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


class InjectionGuard:
    """Detects and redacts suspicious prompt-injection fragments."""

    _category_patterns: tuple[tuple[str, re.Pattern[str]], ...] = (
        (
            "instruction_override",
            re.compile(
                r"(?i)\b(ignore|disregard|forget|override|bypass)\b.*\b(previous|prior|above|system)\b.*"
                r"\b(instruction|prompt|rule)s?\b"
            ),
        ),
        (
            "instruction_override_ru",
            re.compile(
                r"(?i)\b(игнорируй|забудь|отмени|пренебреги|переопредели|обойди)\b.*"
                r"\b(предыдущ|ранн|выше|системн)\w*\b.*\b(инструкц|промпт|правил)\w*\b"
            ),
        ),
        (
            "role_spoofing",
            re.compile(r"(?im)^\s*(system|assistant|developer|tool|function|user)\s*:\s*"),
        ),
        (
            "prompt_leak_attempt",
            re.compile(
                r"(?i)(reveal|print|show|leak).{0,50}(system prompt|hidden prompt|developer prompt)"
            ),
        ),
        (
            "follow_instead",
            re.compile(r"(?i)(follow these instructions instead|ignore above and follow below)"),
        ),
        ("model_format_spoof", re.compile(r"<\|im_start\|>|<\|im_end\|>", re.IGNORECASE)),
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
        diagnostics = cls.scan_diagnostics(normalized)
        if diagnostics:
            return "[REDACTED: suspected prompt injection]", True
        return normalized, False

    @classmethod
    def scan_diagnostics(cls, text: str) -> list[str]:
        normalized = cls.normalize(text)
        if not normalized:
            return []
        findings: set[str] = set()
        for code, pattern in cls._category_patterns:
            if pattern.search(normalized):
                findings.add(code)
        if _HTML_COMMENT_RE.search(normalized):
            findings.add("html_comment_payload")
        if _MARKDOWN_HIDDEN_RE.search(normalized) and "ignore" in normalized.lower():
            findings.add("markdown_hidden_payload")
        if cls._contains_base64_instructions(normalized):
            findings.add("base64_payload")
        if _ZERO_WIDTH_RE.search(text):
            findings.add("zero_width_chars")
        return sorted(findings)

    @staticmethod
    def _contains_base64_instructions(text: str) -> bool:
        for token in re.findall(r"[A-Za-z0-9+/=]{24,}", text):
            try:
                raw = base64.b64decode(token, validate=True)
            except (binascii.Error, ValueError):
                continue
            try:
                decoded = raw.decode("utf-8", errors="ignore").lower()
            except Exception:
                continue
            if any(k in decoded for k in ("ignore previous", "system prompt", "follow these")):
                return True
        return False

    @classmethod
    def is_suspicious(cls, text: str) -> bool:
        return bool(cls.scan_diagnostics(text))

    def contains_prompt_injection(self, text: str) -> bool:
        """Public API: whether snippet looks like a prompt-injection attempt."""
        return self.is_suspicious(text)

    def mask_pii(self, text: str, limit: int = 200) -> str:
        return sanitize_pii(text, limit=limit)


def sanitize_pii(text: str, limit: int = 200) -> str:
    """Trim + mask lightweight PII for safe logging."""

    clipped = text[:limit]
    clipped = _EMAIL_RE.sub("[email]", clipped)
    clipped = _PHONE_RE.sub("[phone]", clipped)
    return clipped
