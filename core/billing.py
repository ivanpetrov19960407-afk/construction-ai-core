"""Billing plans, subscription storage and quota guards."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import create_engine, text

from config.settings import settings
from core.cache import RedisCache
from core.multitenancy import get_tenant_id


class PlanTier(str, Enum):
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


usage_counter = UsageCounter(RedisCache(settings.redis_url))


def _ensure_subscriptions_table() -> None:
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


def get_current_plan(org_id: str) -> tuple[PlanTier, str | None]:
    _ensure_subscriptions_table()
    engine = create_engine(settings.database_url, future=True)
    query = text(
        """
        SELECT plan, valid_until
        FROM org_subscriptions
        WHERE org_id = :org_id
        ORDER BY created_at DESC
        LIMIT 1
        """
    )
    with engine.connect() as conn:
        row = conn.execute(query, {"org_id": org_id}).mappings().first()

    if row is None:
        return PlanTier.FREE, None

    try:
        return PlanTier(str(row["plan"])), row["valid_until"]
    except ValueError:
        return PlanTier.FREE, row["valid_until"]


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
        _ = request
        tenant = org_id or "default"
        actual_plan = _resolve_plan(tenant, plan)
        allowed = await usage_counter.check_limit(tenant, resource, actual_plan)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail=f"Quota exceeded for resource '{resource}' on plan '{actual_plan.value}'",
            )
        await usage_counter.increment(tenant, resource)

    return _dependency

