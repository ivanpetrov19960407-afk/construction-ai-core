"""Compliance API routes for GSN checklist and PDF reporting."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from core.compliance.gsn_checklist import GSNReadinessChecker

router = APIRouter(prefix="/compliance", tags=["compliance"])
checker = GSNReadinessChecker()


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


def _render_gsn_report_html(project_id: str, checklist: dict) -> str:
    template = Path("templates/gsn_checklist.html").read_text(encoding="utf-8")
    rows = "\n".join(_build_section_row(item) for item in checklist["sections"])
    return (
        template.replace("{{ project_id }}", project_id)
        .replace("{{ generated_at }}", datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"))
        .replace("{{ total_completion_pct }}", str(checklist["completion_pct"]))
        .replace("{{ section_rows }}", rows)
    )


def _render_pdf_from_html(html: str) -> bytes:
    try:
        from weasyprint import HTML
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("weasyprint is required for gsn PDF report generation") from exc
    return HTML(string=html, base_url=str(Path.cwd())).write_pdf()


@router.get("/gsn-checklist/{project_id}")
async def get_gsn_checklist(project_id: str) -> dict:
    return await checker.check_full_project(project_id=project_id)


@router.get("/gsn-checklist/{project_id}/section/{section}")
async def get_gsn_checklist_section(project_id: str, section: str) -> dict:
    try:
        return await checker.check_section(project_id=project_id, section=section)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/gsn-report/{project_id}")
async def generate_gsn_report(project_id: str) -> Response:
    checklist = await checker.check_full_project(project_id=project_id)
    html = _render_gsn_report_html(project_id=project_id, checklist=checklist)
    try:
        pdf_bytes = await asyncio.to_thread(_render_pdf_from_html, html)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="gsn_checklist_{project_id}.pdf"'},
    )
