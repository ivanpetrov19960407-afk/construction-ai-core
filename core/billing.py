"""Billing plans, subscription storage and quota guards."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from config.settings import settings
from core.cache import RedisCache
from core.multitenancy import get_tenant_id


class PlanTier(str, Enum):  # noqa: UP042
    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    ENTERPRISE = "enterprise"


PLAN_LIMITS: dict[PlanTier, dict[str, int]] = {
    PlanTier.FREE: {"projects": 1, "ai_requests": 20, "exec_albums": 0},
    PlanTier.STARTER: {"projects": 3, "ai_requests": 100, "exec_albums": 5},
    PlanTier.PRO: {"projects": 20, "ai_requests": 2000, "exec_albums": 50},
    PlanTier.ENTERPRISE: {"projects": -1, "ai_requests": -1, "exec_albums": -1},
}

UTC = getattr(datetime, "UTC", timezone(timedelta(0)))


class BillingPlanResponse(BaseModel):
    org_id: str
    plan: PlanTier
    valid_until: str | None = None


class BillingUsageResponse(BaseModel):
    org_id: str
    plan: PlanTier
    usage: dict[str, int]
    limits: dict[str, int]


class UsageCounter:
    """Счётчик использования ресурсов для org_id через Redis."""

    def __init__(self, redis_cache: RedisCache):
        self._cache = redis_cache

    @staticmethod
    def _month_key() -> str:
        return datetime.now(UTC).strftime("%Y%m")

    def _usage_key(self, org_id: str, resource: str) -> str:
        return f"billing:usage:{org_id}:{resource}:{self._month_key()}"

    async def increment(self, org_id: str, resource: str) -> int:
        current = await self.get_usage(org_id, resource)
        updated = current + 1
        await self._cache.set(
            self._usage_key(org_id, resource),
            str(updated),
            ttl=60 * 60 * 24 * 35,
        )
        return updated

    async def get_usage(self, org_id: str, resource: str) -> int:
        raw = await self._cache.get(self._usage_key(org_id, resource))
        if raw is None:
            return 0
        try:
            return int(raw)
        except ValueError:
            return 0

    async def check_limit(self, org_id: str, resource: str, plan: PlanTier) -> bool:
        limit = PLAN_LIMITS[plan].get(resource)
        if limit is None:
            return True
        if limit == -1:
            return True
        usage = await self.get_usage(org_id, resource)
        return usage < limit

    async def consume_quota(self, org_id: str, resource: str, plan: PlanTier) -> bool:
        """Atomically check + consume quota for a resource."""
        limit = PLAN_LIMITS[plan].get(resource)
        if limit is None:
            return True

        key = self._usage_key(org_id, resource)
        ttl = 60 * 60 * 24 * 35
        redis_client = getattr(self._cache, "_redis", None)
        if redis_client is not None and hasattr(redis_client, "eval"):
            script = """
            local key = KEYS[1]
            local limit = tonumber(ARGV[1])
            local ttl = tonumber(ARGV[2])
            local current = redis.call('GET', key)
            if current == false then
                current = 0
            else
                current = tonumber(current)
            end
            if limit ~= -1 and current >= limit then
                return -1
            end
            local updated = redis.call('INCR', key)
            redis.call('EXPIRE', key, ttl)
            return updated
            """
            try:
                updated = await redis_client.eval(script, 1, key, limit, ttl)
                return int(updated) != -1
            except Exception:  # noqa: BLE001
                # Graceful fallback when Redis host is unavailable in local/CI environments.
                pass

        # Fallback for environments without Redis/Lua support.
        if limit != -1:
            usage = await self.get_usage(org_id, resource)
            if usage >= limit:
                return False
        await self.increment(org_id, resource)
        return True


usage_counter = UsageCounter(RedisCache(settings.redis_url))


def _ensure_sqlite_directory(database_url: str) -> None:
    url = make_url(database_url)
    if url.drivername != "sqlite":
        return
    if not url.database or url.database == ":memory:":
        return
    Path(url.database).parent.mkdir(parents=True, exist_ok=True)


def _ensure_subscriptions_table() -> None:
    _ensure_sqlite_directory(settings.database_url)
    engine = create_engine(settings.database_url, future=True)
    create_table_query = text(
        """
        CREATE TABLE IF NOT EXISTS org_subscriptions (
            id TEXT PRIMARY KEY,
            org_id TEXT NOT NULL,
            plan TEXT NOT NULL,
            valid_until TEXT,
            payment_id TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    with engine.begin() as conn:
        conn.execute(create_table_query)


def _parse_valid_until(raw: str | None) -> datetime | None:
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _is_subscription_active(valid_until: str | None) -> bool:
    parsed = _parse_valid_until(valid_until)
    if parsed is None:
        return True
    return parsed >= datetime.now(UTC)


def get_current_plan(org_id: str) -> tuple[PlanTier, str | None]:
    _ensure_subscriptions_table()
    engine = create_engine(settings.database_url, future=True)
    query = text(
        """
        SELECT plan, valid_until
        FROM org_subscriptions
        WHERE org_id = :org_id
        ORDER BY created_at DESC
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(query, {"org_id": org_id}).mappings().all()

    for row in rows:
        valid_until = row["valid_until"]
        if not _is_subscription_active(valid_until):
            continue
        try:
            return PlanTier(str(row["plan"])), valid_until
        except ValueError:
            continue
    return PlanTier.FREE, None


def set_plan(
    org_id: str,
    plan: PlanTier,
    valid_until: str | None = None,
    payment_id: str = "",
) -> None:
    _ensure_subscriptions_table()
    engine = create_engine(settings.database_url, future=True)
    query = text(
        """
        INSERT INTO org_subscriptions (id, org_id, plan, valid_until, payment_id, created_at)
        VALUES (:id, :org_id, :plan, :valid_until, :payment_id, CURRENT_TIMESTAMP)
        """
    )
    record_id = f"{org_id}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}"
    with engine.begin() as conn:
        conn.execute(
            query,
            {
                "id": record_id,
                "org_id": org_id,
                "plan": plan.value,
                "valid_until": valid_until,
                "payment_id": payment_id,
            },
        )


def _resolve_plan(org_id: str, explicit_plan: PlanTier | None = None) -> PlanTier:
    if explicit_plan is not None:
        return explicit_plan
    plan, _valid_until = get_current_plan(org_id)
    return plan


def require_quota(resource: str, plan: PlanTier | None = None):
    """Dependency для FastAPI: проверить квоту перед выполнением запроса."""

    async def _dependency(
        request: Request,
        org_id: str | None = Depends(get_tenant_id),
    ) -> None:
        tenant = org_id or getattr(request.state, "org_id", None)
        if not tenant:
            api_key = request.headers.get("X-API-Key")
            if api_key and api_key in settings.api_keys:
                tenant = "default"
        if not tenant:
            # For requests without tenant context quota cannot be enforced reliably.
            return
        actual_plan = _resolve_plan(tenant, plan)
        allowed = await usage_counter.consume_quota(tenant, resource, actual_plan)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail=f"Quota exceeded for resource '{resource}' on plan '{actual_plan.value}'",
            )

    return _dependency
