"""Compliance API routes for GSN checklist and PDF reporting."""

from __future__ import annotations

import asyncio
import datetime as dt
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from config.settings import settings
from core.branding import BrandingConfig, get_branding
from core.compliance.gsn_checklist import GSNReadinessChecker
from core.multitenancy import get_tenant_id
from core.projects import Project, get_projects_sessionmaker

router = APIRouter(prefix="/compliance", tags=["compliance"])
checker = GSNReadinessChecker()
UTC = getattr(dt, "UTC", dt.timezone(dt.timedelta(0)))


def _build_section_row(section_result: dict) -> str:
    required = len(section_result["present"]) + len(section_result["missing"])
    present = len(section_result["present"])
    missing = len(section_result["missing"])
    completion_pct = section_result["completion_pct"]
    return (
        "<tr>"
        f"<td>{section_result['section']}</td>"
        f"<td>{required}</td>"
        f"<td>{present}</td>"
        f"<td>{missing}</td>"
        f"<td>{completion_pct}%</td>"
        "</tr>"
    )


def _render_gsn_report_html(project_id: str, checklist: dict, branding: BrandingConfig) -> str:
    template = Path("templates/gsn_checklist.html").read_text(encoding="utf-8")
    rows = "\n".join(_build_section_row(item) for item in checklist["sections"])
    generated_at = dt.datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    return (
        template.replace("{{ project_id }}", project_id)
        .replace("{{ generated_at }}", generated_at)
        .replace("{{ total_completion_pct }}", str(checklist["completion_pct"]))
        .replace("{{ company_name }}", branding.company_name)
        .replace("{{ logo_url }}", branding.logo_url)
        .replace("{{ section_rows }}", rows)
    )


def _render_pdf_from_html(html: str) -> bytes:
    try:
        from weasyprint import HTML
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("weasyprint is required for gsn PDF report generation") from exc
    return HTML(string=html, base_url=str(Path.cwd())).write_pdf()


def _require_project_member(request: Request, project_id: UUID, org_id: str) -> None:
    username = getattr(request.state, "username", None)
    if not username:
        raise HTTPException(status_code=401, detail="Authentication required")

    session_local = get_projects_sessionmaker(settings.sqlite_db_path)
    with session_local() as session:
        project = session.get(Project, project_id)
        if project is None or project.org_id != org_id:
            raise HTTPException(status_code=404, detail="Project not found")

        members = project.members or []
        if username != project.owner_id and username not in members:
            raise HTTPException(status_code=403, detail="Access denied")


@router.get("/gsn-checklist/{project_id}")
async def get_gsn_checklist(
    project_id: UUID,
    request: Request,
    org_id: str | None = Depends(get_tenant_id),
) -> dict:
    _require_project_member(request=request, project_id=project_id, org_id=org_id or "default")
    return await checker.check_full_project(project_id=str(project_id))


@router.get("/gsn-checklist/{project_id}/section/{section}")
async def get_gsn_checklist_section(
    project_id: UUID,
    section: str,
    request: Request,
    org_id: str | None = Depends(get_tenant_id),
) -> dict:
    _require_project_member(request=request, project_id=project_id, org_id=org_id or "default")
    try:
        return await checker.check_section(project_id=str(project_id), section=section)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/gsn-report/{project_id}")
async def generate_gsn_report(
    project_id: UUID,
    request: Request,
    org_id: str | None = Depends(get_tenant_id),
) -> Response:
    _require_project_member(request=request, project_id=project_id, org_id=org_id or "default")
    checklist = await checker.check_full_project(project_id=str(project_id))
    branding = await get_branding(org_id or "default")
    html = _render_gsn_report_html(
        project_id=str(project_id),
        checklist=checklist,
        branding=branding,
    )
    try:
        pdf_bytes = await asyncio.to_thread(_render_pdf_from_html, html)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="gsn_checklist_{project_id}.pdf"'},
    )
