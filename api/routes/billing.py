"""Billing and subscription management endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from config.settings import settings
from core.billing import (
    PLAN_LIMITS,
    BillingPlanResponse,
    BillingUsageResponse,
    PlanTier,
    get_current_plan,
    set_plan,
    usage_counter,
)
from core.multitenancy import get_tenant_id

router = APIRouter(prefix="/billing", tags=["billing"])
UTC = getattr(datetime, "UTC", timezone(timedelta(0)))


class PlanUpdateRequest(BaseModel):
    plan: PlanTier
    valid_until: str | None = None


class YooKassaWebhookRequest(BaseModel):
    event: str
    object: dict[str, Any]


def _require_admin(request: Request) -> None:
    role = getattr(request.state, "user_role", None)
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")


@router.get("/plan", response_model=BillingPlanResponse)
async def get_plan(org_id: str | None = Depends(get_tenant_id)) -> BillingPlanResponse:
    tenant = org_id or "default"
    plan, valid_until = get_current_plan(tenant)
    return BillingPlanResponse(org_id=tenant, plan=plan, valid_until=valid_until)


@router.post("/plan", response_model=BillingPlanResponse)
async def change_plan(
    payload: PlanUpdateRequest,
    request: Request,
    org_id: str | None = Depends(get_tenant_id),
) -> BillingPlanResponse:
    _require_admin(request)
    tenant = org_id or "default"
    set_plan(tenant, payload.plan, valid_until=payload.valid_until)
    plan, valid_until = get_current_plan(tenant)
    return BillingPlanResponse(org_id=tenant, plan=plan, valid_until=valid_until)


@router.get("/usage", response_model=BillingUsageResponse)
async def get_usage(org_id: str | None = Depends(get_tenant_id)) -> BillingUsageResponse:
    tenant = org_id or "default"
    plan, _valid_until = get_current_plan(tenant)
    resources = ["projects", "ai_requests", "exec_albums"]
    usage = {
        resource: await usage_counter.get_usage(tenant, resource)
        for resource in resources
    }
    return BillingUsageResponse(
        org_id=tenant,
        plan=plan,
        usage=usage,
        limits=PLAN_LIMITS[plan],
    )


@router.post("/webhook/yookassa")
async def yookassa_webhook(request: Request, payload: YooKassaWebhookRequest) -> dict[str, bool]:
    configured_secret = settings.yookassa_secret_key.strip()
    if configured_secret:
        signature = request.headers.get("X-YooKassa-Signature", "").strip()
        auth_header = request.headers.get("Authorization", "").strip()
        bearer = auth_header.removeprefix("Bearer ").strip() if auth_header else ""
        if signature != configured_secret and bearer != configured_secret:
            raise HTTPException(status_code=401, detail="Invalid YooKassa webhook signature")

    obj = payload.object
    metadata = obj.get("metadata") if isinstance(obj, dict) else None
    if not isinstance(metadata, dict):
        return {"ok": True}

    org_id = str(metadata.get("org_id", "default"))
    plan_raw = str(metadata.get("plan", PlanTier.FREE.value))

    try:
        plan = PlanTier(plan_raw)
    except ValueError:
        plan = PlanTier.FREE

    if payload.event == "payment.succeeded":
        payment_id = str(obj.get("id", "")) if isinstance(obj, dict) else ""
        valid_until = (datetime.now(UTC) + timedelta(days=30)).isoformat()
        set_plan(org_id, plan, valid_until=valid_until, payment_id=payment_id)

    return {"ok": True}
