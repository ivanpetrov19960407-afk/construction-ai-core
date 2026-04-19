"""Compliance API routes for GSN checklist and PDF reporting."""

from __future__ import annotations

import asyncio
import datetime as dt
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select

from api.deps import CurrentUser, current_user
from core.branding import BrandingConfig, get_branding
from core.multitenancy import get_tenant_id
from core.projects import Project, get_projects_sessionmaker
from config.settings import settings
from core.compliance.gsn_checklist import GSNReadinessChecker

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


def _resolve_project(project_id: str, org_id: str) -> Project:
    session_local = get_projects_sessionmaker(settings.sqlite_db_path)
    with session_local() as session:
        project: Project | None = None
        try:
            parsed_uuid = UUID(project_id)
            project = session.get(Project, parsed_uuid)
        except ValueError:
            if project_id.isdigit():
                project = session.execute(
                    select(Project).where(Project.short_id == int(project_id))
                ).scalar_one_or_none()

        if project is None or project.org_id != org_id:
            raise HTTPException(status_code=404, detail="project_not_found")

        session.expunge(project)
        return project


def _require_project_member(user: CurrentUser, project: Project) -> None:
    members = project.members or []
    if user.username != project.owner_id and user.username not in members:
        raise HTTPException(status_code=403, detail="Access denied")


@router.get("/gsn-checklist/{project_id}")
async def get_gsn_checklist(
    project_id: str,
    user: CurrentUser = Depends(current_user),
    org_id: str | None = Depends(get_tenant_id),
) -> dict:
    project = _resolve_project(project_id=project_id, org_id=org_id or user.org_id or "default")
    _require_project_member(user=user, project=project)
    return await checker.check_full_project(project_id=str(project.id))


@router.get("/gsn-checklist/{project_id}/section/{section}")
async def get_gsn_checklist_section(
    project_id: str,
    section: str,
    user: CurrentUser = Depends(current_user),
    org_id: str | None = Depends(get_tenant_id),
) -> dict:
    project = _resolve_project(project_id=project_id, org_id=org_id or user.org_id or "default")
    _require_project_member(user=user, project=project)
    try:
        return await checker.check_section(project_id=str(project.id), section=section)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/gsn-report/{project_id}")
async def generate_gsn_report(
    project_id: str,
    user: CurrentUser = Depends(current_user),
    org_id: str | None = Depends(get_tenant_id),
) -> Response:
    project = _resolve_project(project_id=project_id, org_id=org_id or user.org_id or "default")
    _require_project_member(user=user, project=project)
    checklist = await checker.check_full_project(project_id=str(project.id))
    branding = await get_branding(org_id or user.org_id or "default")
    html = _render_gsn_report_html(
        project_id=str(project.short_id),
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
