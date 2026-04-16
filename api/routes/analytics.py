"""Analytics API routes for schedule prediction and dashboard summaries."""

from __future__ import annotations

import json
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from config.settings import settings
from core.analytics.schedule_predictor import SchedulePredictor
from core.cache import RedisCache
from core.multitenancy import get_tenant_id
from core.projects import Project, get_projects_sessionmaker

router = APIRouter(prefix="/analytics", tags=["analytics"])

_CACHE_TTL_SECONDS = 6 * 60 * 60
_cache = RedisCache(settings.redis_url)
_predictor = SchedulePredictor()


class RiskItem(BaseModel):
    section: str
    description: str
    severity: Literal["high", "medium", "low"]


class ScheduleAnalyticsResponse(BaseModel):
    avg_delay_days: float
    delay_rate: float
    predicted_completion: str
    risks: list[RiskItem]
    recommendations: list[str]


class AnalyticsDashboardResponse(BaseModel):
    project_id: str
    sections: list[dict]
    forecast: ScheduleAnalyticsResponse


def _require_project_access(request: Request, project_id: str, org_id: str) -> None:
    username = getattr(request.state, "username", None)
    if not username:
        raise HTTPException(status_code=401, detail="Authentication required")

    session_local = get_projects_sessionmaker(settings.sqlite_db_path)
    try:
        project_uuid = UUID(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    with session_local() as session:
        project = session.get(Project, project_uuid)
        if project is None or project.org_id != org_id:
            raise HTTPException(status_code=404, detail="Project not found")
        members = project.members or []
        if username != project.owner_id and username not in members:
            raise HTTPException(status_code=403, detail="Access denied")


@router.get("/schedule/{project_id}", response_model=ScheduleAnalyticsResponse)
async def get_schedule_analytics(
    project_id: str,
    request: Request,
    org_id: str | None = Depends(get_tenant_id),
) -> dict:
    """Return project delay stats and completion forecast."""
    tenant = org_id or "default"
    _require_project_access(request, project_id, tenant)
    key = f"analytics:schedule:{project_id}"
    cached = await _cache.get(key)
    if cached is not None:
        return json.loads(cached)

    prediction = await _predictor.predict_completion(project_id)
    await _cache.set(
        key,
        json.dumps(prediction, ensure_ascii=False),
        ttl=_CACHE_TTL_SECONDS,
    )
    return prediction


@router.get("/dashboard/{project_id}", response_model=AnalyticsDashboardResponse)
async def get_analytics_dashboard(
    project_id: str,
    request: Request,
    org_id: str | None = Depends(get_tenant_id),
) -> dict:
    """Return dashboard summary by KG sections with schedule forecast."""
    tenant = org_id or "default"
    _require_project_access(request, project_id, tenant)
    key = f"analytics:schedule:{project_id}"
    cached = await _cache.get(key)
    if cached is not None:
        forecast = json.loads(cached)
    else:
        forecast = await _predictor.predict_completion(project_id)
        await _cache.set(
            key,
            json.dumps(forecast, ensure_ascii=False),
            ttl=_CACHE_TTL_SECONDS,
        )

    sections = await _predictor.get_section_summary(project_id)
    return {
        "project_id": project_id,
        "sections": sections,
        "forecast": forecast,
    }
