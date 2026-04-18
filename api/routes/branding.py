"""Branding API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from core.branding import BrandingConfig, get_branding, upsert_branding
from core.multitenancy import get_tenant_id

router = APIRouter(prefix="/branding", tags=["branding"])


@router.get("", response_model=BrandingConfig)
async def read_branding(org_id: str | None = Depends(get_tenant_id)) -> BrandingConfig:
    """Return branding config for current org_id."""
    return await get_branding(org_id or "default")


@router.put("", response_model=BrandingConfig)
async def update_branding(
    payload: BrandingConfig,
    request: Request,
    org_id: str | None = Depends(get_tenant_id),
) -> BrandingConfig:
    """Update branding config for current org (admin only)."""
    role = getattr(request.state, "user_role", None)
    if role is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    current_org = org_id or "default"
    if payload.org_id != current_org:
        raise HTTPException(status_code=400, detail="org_id mismatch")

    return await upsert_branding(payload)
