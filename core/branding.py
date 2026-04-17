"""White-label branding configuration helpers."""

from __future__ import annotations

import json
import sqlite3

from pydantic import BaseModel

from config.settings import settings
from core.cache import RedisCache


class BrandingConfig(BaseModel):
    org_id: str
    company_name: str = "Construction AI"
    logo_url: str = ""
    primary_color: str = "#2563eb"
    accent_color: str = "#1d4ed8"
    favicon_url: str = ""
    support_email: str = ""
    custom_domain: str = ""


redis_cache = RedisCache(settings.redis_url)


def _load_from_db(org_id: str) -> BrandingConfig:
    default = BrandingConfig(org_id=org_id)
    try:
        with sqlite3.connect(settings.sqlite_db_path) as conn:
            cursor = conn.execute(
                """
                SELECT org_id, company_name, logo_url, primary_color, accent_color,
                       favicon_url, custom_domain, support_email
                FROM org_branding
                WHERE org_id = ?
                """,
                (org_id,),
            )
            row = cursor.fetchone()
    except sqlite3.Error:
        return default

    if row is None:
        return default

    return BrandingConfig(
        org_id=str(row[0]),
        company_name=str(row[1] or default.company_name),
        logo_url=str(row[2] or ""),
        primary_color=str(row[3] or default.primary_color),
        accent_color=str(row[4] or default.accent_color),
        favicon_url=str(row[5] or ""),
        custom_domain=str(row[6] or ""),
        support_email=str(row[7] or ""),
    )


async def get_branding(org_id: str) -> BrandingConfig:
    """Получить конфигурацию брендинга из Redis (TTL 1ч) или БД."""
    normalized_org_id = org_id or "default"
    cache_key = f"branding:{normalized_org_id}"

    cached = await redis_cache.get(cache_key)
    if cached:
        try:
            return BrandingConfig.model_validate_json(cached)
        except (json.JSONDecodeError, ValueError):
            pass

    branding = _load_from_db(normalized_org_id)
    await redis_cache.set(cache_key, branding.model_dump_json(), ttl=3600)
    return branding


async def upsert_branding(branding: BrandingConfig) -> BrandingConfig:
    """Create or update branding config in DB and refresh cache."""
    with sqlite3.connect(settings.sqlite_db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS org_branding (
              org_id TEXT PRIMARY KEY,
              company_name TEXT NOT NULL,
              logo_url TEXT NOT NULL DEFAULT '',
              primary_color TEXT NOT NULL DEFAULT '#2563eb',
              accent_color TEXT NOT NULL DEFAULT '#1d4ed8',
              favicon_url TEXT NOT NULL DEFAULT '',
              custom_domain TEXT NOT NULL DEFAULT '',
              support_email TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute(
            """
            INSERT INTO org_branding (
              org_id, company_name, logo_url, primary_color, accent_color,
              favicon_url, custom_domain, support_email
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(org_id) DO UPDATE SET
              company_name = excluded.company_name,
              logo_url = excluded.logo_url,
              primary_color = excluded.primary_color,
              accent_color = excluded.accent_color,
              favicon_url = excluded.favicon_url,
              custom_domain = excluded.custom_domain,
              support_email = excluded.support_email
            """,
            (
                branding.org_id,
                branding.company_name,
                branding.logo_url,
                branding.primary_color,
                branding.accent_color,
                branding.favicon_url,
                branding.custom_domain,
                branding.support_email,
            ),
        )
        conn.commit()

    await redis_cache.set(f"branding:{branding.org_id}", branding.model_dump_json(), ttl=3600)
    return branding
