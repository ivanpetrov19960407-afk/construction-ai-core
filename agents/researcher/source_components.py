from __future__ import annotations

import hashlib
import re
import socket
from ipaddress import ip_address
from urllib.parse import urlparse

from schemas.research import ResearchSource

_IP_LITERAL_RE = re.compile(r"^[0-9a-fA-F:.]+$")

_WHITESPACE_RE = re.compile(r"\s+")
_SUSPICIOUS_HOST_RE = re.compile(r"(?i)(localhost|\.local$|internal|\.internal$)")


class URLValidator:
    @staticmethod
    def is_allowed(url: str) -> bool:
        if not url:
            return False
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return False

        host = (parsed.hostname or "").strip().rstrip(".")
        if not host or _SUSPICIOUS_HOST_RE.search(host):
            return False

        try:
            host = host.encode("idna").decode("ascii")
        except UnicodeError:
            return False
        if host == "localhost":
            return False

        if _IP_LITERAL_RE.match(host):
            return not _is_private_ip(ip_address(host))

        try:
            infos = socket.getaddrinfo(
                host, parsed.port or 443, proto=socket.IPPROTO_TCP
            )
        except OSError:
            return False
        return all(not _is_private_ip(ip_address(info[4][0])) for info in infos)


class SourceDeduplicator:
    @staticmethod
    def deduplicate_rag(sources: list[ResearchSource]) -> list[ResearchSource]:
        dedup: dict[tuple[str, int, str], ResearchSource] = {}
        for source in sources:
            text_hash = hashlib.sha256((source.snippet or "").encode()).hexdigest()[:12]
            key = ((source.document or "").lower(), source.page or -1, text_hash)
            existing = dedup.get(key)
            if existing is None or source.score > existing.score:
                dedup[key] = source
        return list(dedup.values())


class SourceSanitizer:
    SENSITIVE_FIELDS = (
        "title",
        "document",
        "section",
        "locator",
        "snippet",
        "chunk_text",
        "full_text",
    )

    @classmethod
    def sanitize(
        cls, source: ResearchSource, sanitize_text
    ) -> tuple[ResearchSource, bool]:
        updates: dict[str, str | None] = {}
        flagged = False
        for field in cls.SENSITIVE_FIELDS:
            raw = getattr(source, field) or ""
            clean, redacted = sanitize_text(raw)
            updates[field] = clean
            flagged = flagged or redacted
        return source.model_copy(update=updates), flagged


class SourceTruncator:
    @staticmethod
    def truncate(
        sources: list[ResearchSource], max_prompt_chars: int
    ) -> list[ResearchSource]:
        total_chars = sum(len(s.snippet or "") for s in sources)
        if total_chars <= max_prompt_chars:
            return sources

        ratio = max_prompt_chars / max(total_chars, 1)
        return [
            source.model_copy(
                update={
                    "snippet": (source.snippet or "")[
                        : max(50, int(len(source.snippet or "") * ratio))
                    ]
                }
            )
            for source in sources
        ]


class CacheKeyBuilder:
    @staticmethod
    def build(
        *,
        query: str,
        topic_scope: str | None,
        access_scope: str | None,
        context: str,
        cache_schema_version: int,
        cache_embedding_version: str,
        security_policy_version: str,
        user_id: str | None,
        org_id: str | None,
        tenant_id: str | None,
        project_id: str | None,
    ) -> str:
        norm_query = _WHITESPACE_RE.sub(" ", query).strip().lower()
        query_hash = hashlib.sha256(f"{norm_query}|{context}".encode()).hexdigest()[:16]
        scope_hash = hashlib.sha256(
            f"{topic_scope or ''}|{access_scope or ''}".encode()
        ).hexdigest()[:12]
        identity = "|".join(
            [
                f"user:{user_id or ''}",
                f"org:{org_id or ''}",
                f"tenant:{tenant_id or ''}",
                f"project:{project_id or ''}",
            ]
        )
        identity_hash = hashlib.sha256(identity.encode()).hexdigest()[:12]
        return (
            f"research:{cache_schema_version}:{cache_embedding_version}:{security_policy_version}:"
            f"{query_hash}:{scope_hash}:{identity_hash}"
        )


def _is_private_ip(ip) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
    )
