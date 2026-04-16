"""API routes for collaborative projects."""

from __future__ import annotations

import datetime as dt
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import desc

from config.settings import settings
from core.multitenancy import get_tenant_id
from core.projects import Project, ProjectComment, ProjectDocument, get_projects_sessionmaker

router = APIRouter(prefix="/projects", tags=["projects"])
UTC = getattr(dt, "UTC", dt.timezone(dt.timedelta(0)))


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    members: list[str] = Field(default_factory=list)


class AddMemberRequest(BaseModel):
    member_id: str = Field(min_length=1)


class AddDocumentRequest(BaseModel):
    document_type: str
    session_id: str
    title: str
    version: int = 1


class AddCommentRequest(BaseModel):
    text: str = Field(min_length=1)


def _require_username(request: Request) -> str:
    username = getattr(request.state, "username", None)
    if not username:
        raise HTTPException(status_code=401, detail="Authentication required")
    return str(username)


def _serialize_project(project: Project) -> dict:
    members = list(project.members or [])
    if project.owner_id not in members:
        members.append(project.owner_id)
    return {
        "id": str(project.id),
        "name": project.name,
        "description": project.description,
        "org_id": project.org_id,
        "owner_id": project.owner_id,
        "created_at": project.created_at.isoformat(),
        "members": sorted(set(members)),
    }


def _serialize_document(document: ProjectDocument) -> dict:
    return {
        "id": str(document.id),
        "project_id": str(document.project_id),
        "document_type": document.document_type,
        "session_id": document.session_id,
        "created_by": document.created_by,
        "created_at": document.created_at.isoformat(),
        "title": document.title,
        "version": document.version,
    }


@router.post("", status_code=201)
async def create_project(
    payload: CreateProjectRequest,
    request: Request,
    org_id: str | None = Depends(get_tenant_id),
) -> dict:
    owner = _require_username(request)
    tenant = org_id or "default"
    session_local = get_projects_sessionmaker(settings.sqlite_db_path)

    members = sorted(set(payload.members + [owner]))

    with session_local() as session:
        project = Project(
            name=payload.name,
            description=payload.description,
            org_id=tenant,
            owner_id=owner,
            members=members,
        )
        session.add(project)
        session.commit()
        session.refresh(project)
        return _serialize_project(project)


@router.get("")
async def list_projects(
    request: Request,
    org_id: str | None = Depends(get_tenant_id),
) -> dict[str, list[dict]]:
    username = _require_username(request)
    tenant = org_id or "default"
    session_local = get_projects_sessionmaker(settings.sqlite_db_path)

    with session_local() as session:
        projects = (
            session.query(Project)
            .filter(Project.org_id == tenant)
            .order_by(desc(Project.created_at))
            .all()
        )
        visible = [p for p in projects if username == p.owner_id or username in (p.members or [])]
        return {"projects": [_serialize_project(project) for project in visible]}


@router.get("/{project_id}")
async def get_project(
    project_id: UUID,
    request: Request,
    org_id: str | None = Depends(get_tenant_id),
) -> dict:
    username = _require_username(request)
    tenant = org_id or "default"
    session_local = get_projects_sessionmaker(settings.sqlite_db_path)

    with session_local() as session:
        project = session.get(Project, project_id)
        if project is None or project.org_id != tenant:
            raise HTTPException(status_code=404, detail="Project not found")
        members = project.members or []
        if username != project.owner_id and username not in members:
            raise HTTPException(status_code=403, detail="Access denied")
        return _serialize_project(project)


@router.post("/{project_id}/members")
async def add_project_member(
    project_id: UUID,
    payload: AddMemberRequest,
    request: Request,
    org_id: str | None = Depends(get_tenant_id),
) -> dict:
    username = _require_username(request)
    tenant = org_id or "default"
    session_local = get_projects_sessionmaker(settings.sqlite_db_path)

    with session_local() as session:
        project = session.get(Project, project_id)
        if project is None or project.org_id != tenant:
            raise HTTPException(status_code=404, detail="Project not found")
        if username != project.owner_id:
            raise HTTPException(status_code=403, detail="Only owner can add members")

        members = set(project.members or [])
        members.add(project.owner_id)
        members.add(payload.member_id)
        project.members = sorted(members)
        session.add(project)
        session.commit()
        session.refresh(project)
        return _serialize_project(project)


@router.post("/{project_id}/documents", status_code=201)
async def add_project_document(
    project_id: UUID,
    payload: AddDocumentRequest,
    request: Request,
    org_id: str | None = Depends(get_tenant_id),
) -> dict:
    username = _require_username(request)
    tenant = org_id or "default"
    session_local = get_projects_sessionmaker(settings.sqlite_db_path)

    with session_local() as session:
        project = session.get(Project, project_id)
        if project is None or project.org_id != tenant:
            raise HTTPException(status_code=404, detail="Project not found")
        members = project.members or []
        if username != project.owner_id and username not in members:
            raise HTTPException(status_code=403, detail="Access denied")

        document = ProjectDocument(
            project_id=project.id,
            document_type=payload.document_type,
            session_id=payload.session_id,
            created_by=username,
            title=payload.title,
            version=payload.version,
        )
        session.add(document)
        session.commit()
        session.refresh(document)
        return _serialize_document(document)


@router.get("/{project_id}/documents")
async def list_project_documents(
    project_id: UUID,
    request: Request,
    org_id: str | None = Depends(get_tenant_id),
) -> dict[str, list[dict]]:
    username = _require_username(request)
    tenant = org_id or "default"
    session_local = get_projects_sessionmaker(settings.sqlite_db_path)

    with session_local() as session:
        project = session.get(Project, project_id)
        if project is None or project.org_id != tenant:
            raise HTTPException(status_code=404, detail="Project not found")
        members = project.members or []
        if username != project.owner_id and username not in members:
            raise HTTPException(status_code=403, detail="Access denied")

        documents = (
            session.query(ProjectDocument)
            .filter(ProjectDocument.project_id == project.id)
            .order_by(desc(ProjectDocument.created_at))
            .all()
        )
        return {"documents": [_serialize_document(document) for document in documents]}


@router.post("/{project_id}/documents/{doc_id}/comments", status_code=201)
async def add_document_comment(
    project_id: UUID,
    doc_id: UUID,
    payload: AddCommentRequest,
    request: Request,
    org_id: str | None = Depends(get_tenant_id),
) -> dict:
    username = _require_username(request)
    tenant = org_id or "default"
    session_local = get_projects_sessionmaker(settings.sqlite_db_path)

    with session_local() as session:
        project = session.get(Project, project_id)
        if project is None or project.org_id != tenant:
            raise HTTPException(status_code=404, detail="Project not found")
        members = project.members or []
        if username != project.owner_id and username not in members:
            raise HTTPException(status_code=403, detail="Access denied")

        document = session.get(ProjectDocument, doc_id)
        if document is None or document.project_id != project.id:
            raise HTTPException(status_code=404, detail="Document not found")

        comment = ProjectComment(document_id=doc_id, author=username, text=payload.text)
        session.add(comment)
        session.commit()
        session.refresh(comment)
        return {
            "id": str(comment.id),
            "document_id": str(comment.document_id),
            "author": comment.author,
            "text": comment.text,
            "created_at": comment.created_at.isoformat(),
        }


@router.get("/{project_id}/history")
async def get_project_history(
    project_id: UUID,
    request: Request,
    org_id: str | None = Depends(get_tenant_id),
) -> dict[str, list[dict]]:
    username = _require_username(request)
    tenant = org_id or "default"
    session_local = get_projects_sessionmaker(settings.sqlite_db_path)

    with session_local() as session:
        project = session.get(Project, project_id)
        if project is None or project.org_id != tenant:
            raise HTTPException(status_code=404, detail="Project not found")
        members = project.members or []
        if username != project.owner_id and username not in members:
            raise HTTPException(status_code=403, detail="Access denied")

        entries: list[dict] = [
            {
                "type": "project_created",
                "created_at": project.created_at,
                "actor": project.owner_id,
                "text": f"Project '{project.name}' created",
            }
        ]

        documents = (
            session.query(ProjectDocument)
            .filter(ProjectDocument.project_id == project.id)
            .order_by(desc(ProjectDocument.created_at))
            .limit(50)
            .all()
        )
        for document in documents:
            entries.append(
                {
                    "type": "document_added",
                    "created_at": document.created_at,
                    "actor": document.created_by,
                    "text": f"Document '{document.title}' added (v{document.version})",
                    "document_id": str(document.id),
                }
            )

        if documents:
            doc_ids = [document.id for document in documents]
            comments = (
                session.query(ProjectComment)
                .filter(ProjectComment.document_id.in_(doc_ids))
                .order_by(desc(ProjectComment.created_at))
                .limit(50)
                .all()
            )
            for comment in comments:
                entries.append(
                    {
                        "type": "comment_added",
                        "created_at": comment.created_at,
                        "actor": comment.author,
                        "text": comment.text,
                        "document_id": str(comment.document_id),
                    }
                )

        entries.sort(key=lambda item: item["created_at"], reverse=True)
        serialized = []
        for item in entries[:50]:
            ts = item["created_at"]
            if isinstance(ts, dt.datetime):
                created_at = ts.astimezone(UTC).isoformat()
            else:
                created_at = str(ts)
            row = dict(item)
            row["created_at"] = created_at
            serialized.append(row)
        return {"history": serialized}
