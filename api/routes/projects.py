"""API routes for collaborative projects."""

from __future__ import annotations

import datetime as dt
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, text

from api.deps import CurrentUser, current_user
from config.settings import settings
from core.billing import get_current_plan, usage_counter
from core.multitenancy import get_tenant_id
from core.projects import Project, ProjectComment, ProjectDocument, get_projects_sessionmaker

router = APIRouter(prefix="/projects", tags=["projects"])
UTC = getattr(dt, "UTC", dt.timezone(dt.timedelta(0)))


async def _require_projects_quota(
    user: CurrentUser = Depends(current_user),
    org_id: str | None = Depends(get_tenant_id),
) -> None:
    tenant = org_id or user.org_id or "default"
    plan, _valid_until = get_current_plan(tenant)
    allowed = await usage_counter.consume_quota(tenant, "projects", plan)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Quota exceeded for resource 'projects' on plan '{plan.value}'",
        )


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


def _allocate_short_id(session) -> int:
    session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS project_short_id_seq (
                id INTEGER PRIMARY KEY AUTOINCREMENT
            )
            """
        )
    )
    session.execute(text("INSERT INTO project_short_id_seq DEFAULT VALUES"))
    return int(session.execute(text("SELECT last_insert_rowid()")).scalar_one())


def _serialize_project(project: Project) -> dict:
    members = list(project.members or [])
    if project.owner_id not in members:
        members.append(project.owner_id)
    return {
        "id": str(project.id),
        "short_id": project.short_id,
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
    user: CurrentUser = Depends(current_user),
    org_id: str | None = Depends(get_tenant_id),
    _quota: None = Depends(_require_projects_quota),
) -> dict:
    _ = _quota
    tenant = org_id or user.org_id or "default"
    session_local = get_projects_sessionmaker(settings.sqlite_db_path)

    members = sorted(set(payload.members + [user.username]))

    with session_local() as session:
        next_short_id = _allocate_short_id(session)
        project = Project(
            name=payload.name,
            description=payload.description,
            org_id=tenant,
            owner_id=user.username,
            members=members,
            short_id=next_short_id,
        )
        session.add(project)
        session.commit()
        session.refresh(project)
        return _serialize_project(project)


@router.get("")
async def list_projects(
    user: CurrentUser = Depends(current_user),
    org_id: str | None = Depends(get_tenant_id),
) -> dict[str, list[dict]]:
    tenant = org_id or user.org_id or "default"
    session_local = get_projects_sessionmaker(settings.sqlite_db_path)

    with session_local() as session:
        projects = (
            session.query(Project)
            .filter(Project.org_id == tenant)
            .order_by(desc(Project.created_at))
            .all()
        )
        visible = [
            project
            for project in projects
            if user.username == project.owner_id or user.username in (project.members or [])
        ]
        return {"projects": [_serialize_project(project) for project in visible]}


@router.get("/mine")
async def list_my_projects(
    user: CurrentUser = Depends(current_user),
    org_id: str | None = Depends(get_tenant_id),
) -> dict[str, list[dict]]:
    return await list_projects(user=user, org_id=org_id)


@router.get("/{project_id}")
async def get_project(
    project_id: UUID,
    user: CurrentUser = Depends(current_user),
    org_id: str | None = Depends(get_tenant_id),
) -> dict:
    tenant = org_id or user.org_id or "default"
    session_local = get_projects_sessionmaker(settings.sqlite_db_path)

    with session_local() as session:
        project = session.get(Project, project_id)
        if project is None or project.org_id != tenant:
            raise HTTPException(status_code=404, detail="Project not found")
        members = project.members or []
        if user.username != project.owner_id and user.username not in members:
            raise HTTPException(status_code=403, detail="Access denied")
        return _serialize_project(project)


@router.post("/{project_id}/members")
async def add_project_member(
    project_id: UUID,
    payload: AddMemberRequest,
    user: CurrentUser = Depends(current_user),
    org_id: str | None = Depends(get_tenant_id),
) -> dict:
    tenant = org_id or user.org_id or "default"
    session_local = get_projects_sessionmaker(settings.sqlite_db_path)

    with session_local() as session:
        project = session.get(Project, project_id)
        if project is None or project.org_id != tenant:
            raise HTTPException(status_code=404, detail="Project not found")
        if user.username != project.owner_id:
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
    user: CurrentUser = Depends(current_user),
    org_id: str | None = Depends(get_tenant_id),
) -> dict:
    tenant = org_id or user.org_id or "default"
    session_local = get_projects_sessionmaker(settings.sqlite_db_path)

    with session_local() as session:
        project = session.get(Project, project_id)
        if project is None or project.org_id != tenant:
            raise HTTPException(status_code=404, detail="Project not found")
        members = project.members or []
        if user.username != project.owner_id and user.username not in members:
            raise HTTPException(status_code=403, detail="Access denied")

        document = ProjectDocument(
            project_id=project.id,
            document_type=payload.document_type,
            session_id=payload.session_id,
            created_by=user.username,
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
    user: CurrentUser = Depends(current_user),
    org_id: str | None = Depends(get_tenant_id),
) -> dict[str, list[dict]]:
    tenant = org_id or user.org_id or "default"
    session_local = get_projects_sessionmaker(settings.sqlite_db_path)

    with session_local() as session:
        project = session.get(Project, project_id)
        if project is None or project.org_id != tenant:
            raise HTTPException(status_code=404, detail="Project not found")
        members = project.members or []
        if user.username != project.owner_id and user.username not in members:
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
    user: CurrentUser = Depends(current_user),
    org_id: str | None = Depends(get_tenant_id),
) -> dict:
    tenant = org_id or user.org_id or "default"
    session_local = get_projects_sessionmaker(settings.sqlite_db_path)

    with session_local() as session:
        project = session.get(Project, project_id)
        if project is None or project.org_id != tenant:
            raise HTTPException(status_code=404, detail="Project not found")
        members = project.members or []
        if user.username != project.owner_id and user.username not in members:
            raise HTTPException(status_code=403, detail="Access denied")

        document = session.get(ProjectDocument, doc_id)
        if document is None or document.project_id != project.id:
            raise HTTPException(status_code=404, detail="Document not found")

        comment = ProjectComment(document_id=doc_id, author=user.username, text=payload.text)
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
    user: CurrentUser = Depends(current_user),
    org_id: str | None = Depends(get_tenant_id),
) -> dict[str, list[dict]]:
    tenant = org_id or user.org_id or "default"
    session_local = get_projects_sessionmaker(settings.sqlite_db_path)

    with session_local() as session:
        project = session.get(Project, project_id)
        if project is None or project.org_id != tenant:
            raise HTTPException(status_code=404, detail="Project not found")
        members = project.members or []
        if user.username != project.owner_id and user.username not in members:
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
