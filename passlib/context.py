"""Minimal CryptContext replacement for offline tests."""

from __future__ import annotations

import hashlib


class CryptContext:
    """Subset of passlib.context.CryptContext used by this project."""

    def __init__(self, schemes: list[str] | None = None, deprecated: str | None = None):
        self.schemes = schemes or []
        self.deprecated = deprecated

    def hash(self, password: str) -> str:
        digest = hashlib.sha256(password.encode("utf-8")).hexdigest()
        return f"sha256${digest}"

    def verify(self, password: str, hashed: str) -> bool:
        return self.hash(password) == hashed
