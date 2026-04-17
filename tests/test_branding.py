"""Tests for white-label branding API and template integration."""

from __future__ import annotations

import asyncio
import datetime as dt

from fastapi.testclient import TestClient

from api.main import app
from api.routes import compliance
from api.security import encode_jwt
from config.settings import settings
from core.branding import BrandingConfig, get_branding

UTC = getattr(dt, "UTC", dt.timezone(dt.timedelta(0)))


def _make_bearer(username: str, role: str, org_id: str = "default") -> str:
    payload = {
        "sub": username,
        "role": role,
        "org_id": org_id,
        "exp": int((dt.datetime.now(UTC) + dt.timedelta(hours=1)).timestamp()),
    }
    return encode_jwt(payload, settings.jwt_secret, algorithm="HS256")


def test_get_default_branding(tmp_path):
    old_db_path = settings.sqlite_db_path
    settings.sqlite_db_path = str(tmp_path / "branding_default.db")

    try:
        branding = asyncio.run(get_branding("acme"))
    finally:
        settings.sqlite_db_path = old_db_path

    assert branding.org_id == "acme"
    assert branding.company_name == "Construction AI"
    assert branding.primary_color == "#2563eb"


def test_update_branding_admin_only(tmp_path):
    old_db_path = settings.sqlite_db_path
    old_keys = settings.api_keys
    old_secret = settings.jwt_secret
    settings.sqlite_db_path = str(tmp_path / "branding_api.db")
    settings.api_keys = ["valid-key"]
    settings.jwt_secret = "z" * 32

    payload = {
        "org_id": "org-alpha",
        "company_name": "Alpha Build",
        "logo_url": "https://cdn.example/logo.png",
        "primary_color": "#111111",
        "accent_color": "#222222",
        "favicon_url": "",
        "support_email": "support@alpha.example",
        "custom_domain": "alpha.example",
    }

    try:
        with TestClient(app) as client:
            forbidden = client.put(
                "/api/branding",
                json=payload,
                headers={
                    "Authorization": f"Bearer {_make_bearer('user', 'pto_engineer', 'org-alpha')}"
                },
            )
            allowed = client.put(
                "/api/branding",
                json=payload,
                headers={"Authorization": f"Bearer {_make_bearer('admin', 'admin', 'org-alpha')}"},
            )
            fetched = client.get(
                "/api/branding",
                headers={"Authorization": f"Bearer {_make_bearer('admin', 'admin', 'org-alpha')}"},
            )
    finally:
        settings.sqlite_db_path = old_db_path
        settings.api_keys = old_keys
        settings.jwt_secret = old_secret

    assert forbidden.status_code == 403
    assert allowed.status_code == 200
    assert fetched.status_code == 200
    assert fetched.json()["company_name"] == "Alpha Build"


def test_branding_in_pdf_template():
    checklist = {
        "sections": [
            {
                "section": "KZH",
                "present": [1, 2],
                "missing": [3],
                "completion_pct": 66.7,
            }
        ],
        "completion_pct": 66.7,
    }
    branding = BrandingConfig(
        org_id="org-x",
        company_name="ООО Альфа Строй",
        logo_url="https://cdn.example/alpha.svg",
    )

    html = compliance._render_gsn_report_html(
        project_id="project-42",
        checklist=checklist,
        branding=branding,
    )

    assert "ООО Альфа Строй" in html
    assert "https://cdn.example/alpha.svg" in html
