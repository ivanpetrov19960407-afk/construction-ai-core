"""Tests for GSN compliance checklist and report API."""

from __future__ import annotations

import asyncio
import datetime as dt
import sqlite3
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from api.main import app
from api.routes import compliance
from api.security import encode_jwt
from config.settings import settings
from core.compliance.gsn_checklist import GSN_REQUIREMENTS, GSNReadinessChecker
from core.projects import Project, ProjectDocument, get_projects_sessionmaker

UTC = getattr(dt, "UTC", dt.timezone(dt.timedelta(0)))




def _bind_api_key_user(api_key: str, username: str) -> None:
    users_db = Path(settings.users_db_path)
    users_db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(users_db) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS api_keys (
                api_key TEXT PRIMARY KEY,
                user_id TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT OR REPLACE INTO api_keys (api_key, user_id) VALUES (?, ?)",
            (api_key, username),
        )
        connection.commit()

def _make_bearer(username: str, role: str = "pto_engineer") -> str:
    payload = {
        "sub": username,
        "role": role,
        "exp": int((dt.datetime.now(UTC) + dt.timedelta(hours=1)).timestamp()),
    }
    return encode_jwt(payload, settings.jwt_secret, algorithm="HS256")


def _seed_project_docs(
    sqlite_path: str,
    section: str,
    include_journals: bool = True,
    owner: str = "tester",
) -> str:
    session_local = get_projects_sessionmaker(sqlite_path)
    project_id = uuid4()

    with session_local() as session:
        session.add(
            Project(
                id=project_id,
                short_id=11,
                name="GSN Project",
                description="",
                owner_id=owner,
                members=[owner],
            )
        )

        requirements = GSN_REQUIREMENTS[section]
        for requirement_key in ("required_acts", "required_schemes", "required_passports"):
            for requirement in requirements[requirement_key]:
                session.add(
                    ProjectDocument(
                        project_id=project_id,
                        document_type=f"{section} {requirement_key}",
                        session_id="sess-1",
                        created_by=owner,
                        title=f"{section} {requirement}",
                        version=1,
                    )
                )

        if include_journals:
            for requirement in requirements["required_journals"]:
                session.add(
                    ProjectDocument(
                        project_id=project_id,
                        document_type=f"{section} required_journals",
                        session_id="sess-1",
                        created_by=owner,
                        title=f"{section} {requirement}",
                        version=1,
                    )
                )

        session.commit()

    return str(project_id)


def test_gsn_checklist_complete(tmp_path):
    old_db_path = settings.sqlite_db_path
    settings.sqlite_db_path = str(tmp_path / "compliance_complete.db")
    try:
        project_id = _seed_project_docs(
            settings.sqlite_db_path,
            section="KZH",
            include_journals=True,
        )
        checker = GSNReadinessChecker()
        result = asyncio.run(checker.check_section(project_id=project_id, section="KZH"))
    finally:
        settings.sqlite_db_path = old_db_path

    assert result["ready"] is True
    assert result["missing"] == []
    assert result["completion_pct"] == 100.0


def test_gsn_checklist_missing(tmp_path):
    old_db_path = settings.sqlite_db_path
    settings.sqlite_db_path = str(tmp_path / "compliance_missing.db")
    try:
        project_id = _seed_project_docs(
            settings.sqlite_db_path,
            section="KZH",
            include_journals=False,
        )
        checker = GSNReadinessChecker()
        result = asyncio.run(checker.check_section(project_id=project_id, section="KZH"))
    finally:
        settings.sqlite_db_path = old_db_path

    assert result["ready"] is False
    missing_journal_names = {
        item["name"] for item in result["missing"] if item["type"] == "journal"
    }
    assert missing_journal_names == set(GSN_REQUIREMENTS["KZH"]["required_journals"])


def test_gsn_report_pdf(tmp_path, monkeypatch):
    old_db_path = settings.sqlite_db_path
    old_keys = settings.api_keys
    old_secret = settings.jwt_secret
    settings.sqlite_db_path = str(tmp_path / "compliance_api.db")
    settings.api_keys = ["valid-key"]
    settings.jwt_secret = "x" * 32

    project_id = _seed_project_docs(
        settings.sqlite_db_path,
        section="KZH",
        include_journals=True,
    )

    monkeypatch.setattr(compliance, "checker", GSNReadinessChecker())
    monkeypatch.setattr(compliance, "_render_pdf_from_html", lambda _html: b"%PDF-1.4\nmock")

    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/compliance/gsn-report/{project_id}",
                headers={"Authorization": f"Bearer {_make_bearer('tester')}"},
            )
    finally:
        settings.sqlite_db_path = old_db_path
        settings.api_keys = old_keys
        settings.jwt_secret = old_secret

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")


def test_gsn_checklist_requires_membership(tmp_path, monkeypatch):
    old_db_path = settings.sqlite_db_path
    old_secret = settings.jwt_secret
    settings.sqlite_db_path = str(tmp_path / "compliance_access.db")
    settings.jwt_secret = "y" * 32

    project_id = _seed_project_docs(
        settings.sqlite_db_path,
        section="KZH",
        include_journals=True,
        owner="owner",
    )
    monkeypatch.setattr(compliance, "checker", GSNReadinessChecker())

    try:
        with TestClient(app) as client:
            forbidden = client.get(
                f"/api/compliance/gsn-checklist/{project_id}",
                headers={"Authorization": f"Bearer {_make_bearer('outsider')}"},
            )
            missing_project = client.get(
                f"/api/compliance/gsn-checklist/{uuid4()}",
                headers={"Authorization": f"Bearer {_make_bearer('owner')}"},
            )
            malformed = client.get(
                "/api/compliance/gsn-checklist/does-not-exist",
                headers={"Authorization": f"Bearer {_make_bearer('owner')}"},
            )
    finally:
        settings.sqlite_db_path = old_db_path
        settings.jwt_secret = old_secret

    assert forbidden.status_code == 403
    assert missing_project.status_code == 404
    assert malformed.status_code == 404
    assert malformed.json() == {"detail": "project_not_found"}


def test_gsn_checklist_short_id_with_api_key(tmp_path, monkeypatch):
    old_db_path = settings.sqlite_db_path
    old_users_db = settings.users_db_path
    old_keys = settings.api_keys

    settings.sqlite_db_path = str(tmp_path / "compliance_short_id.db")
    settings.users_db_path = str(tmp_path / "users.db")
    settings.api_keys = ["desktop-key"]

    project_id = _seed_project_docs(
        settings.sqlite_db_path,
        section="KZH",
        include_journals=True,
        owner="tester",
    )
    _ = project_id
    _bind_api_key_user("desktop-key", "tester")
    monkeypatch.setattr(compliance, "checker", GSNReadinessChecker())

    try:
        with TestClient(app) as client:
            ok = client.get(
                "/api/compliance/gsn-checklist/11",
                headers={"X-API-Key": "desktop-key"},
            )
            not_found = client.get(
                "/api/compliance/gsn-checklist/does-not-exist",
                headers={"X-API-Key": "desktop-key"},
            )
    finally:
        settings.sqlite_db_path = old_db_path
        settings.users_db_path = old_users_db
        settings.api_keys = old_keys

    assert ok.status_code == 200
    assert not_found.status_code == 404
    assert not_found.json() == {"detail": "project_not_found"}
