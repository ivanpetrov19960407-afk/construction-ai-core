"""SQLAlchemy models and storage helpers for team projects."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Integer, String, create_engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)

UTC = getattr(dt, "UTC", dt.timezone(dt.timedelta(0)))


class Base(DeclarativeBase):
    """Base SQLAlchemy model class."""


class Project(Base):
    """Collaborative project model."""

    __tablename__ = "projects"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(String(2000), default="", nullable=False)
    org_id: Mapped[str] = mapped_column(String(255), nullable=False, default="default", index=True)
    owner_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    short_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True, index=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: dt.datetime.now(UTC),
    )
    members: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    documents: Mapped[list[ProjectDocument]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )


class ProjectDocument(Base):
    """Document attached to project."""

    __tablename__ = "project_documents"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
    )
    document_type: Mapped[str] = mapped_column(String(120), nullable=False)
    session_id: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: dt.datetime.now(UTC),
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    project: Mapped[Project] = relationship(back_populates="documents")
    comments: Mapped[list[ProjectComment]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )


class ProjectComment(Base):
    """Comment for a project document."""

    __tablename__ = "project_comments"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("project_documents.id", ondelete="CASCADE"),
        index=True,
    )
    author: Mapped[str] = mapped_column(String(255), nullable=False)
    text: Mapped[str] = mapped_column(String(4000), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: dt.datetime.now(UTC),
    )

    document: Mapped[ProjectDocument] = relationship(back_populates="comments")


_ENGINE_CACHE: dict[str, object] = {}
_SESSIONMAKER_CACHE: dict[str, sessionmaker[Session]] = {}


def _normalized_sqlite_url(db_path: str) -> str:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path}"


def get_projects_sessionmaker(db_path: str) -> sessionmaker[Session]:
    """Return cached SQLAlchemy session factory for projects database."""
    if db_path not in _SESSIONMAKER_CACHE:
        url = _normalized_sqlite_url(db_path)
        engine = create_engine(url, future=True)
        Base.metadata.create_all(engine)
        _ENGINE_CACHE[db_path] = engine
        _SESSIONMAKER_CACHE[db_path] = sessionmaker(
            bind=engine,
            autoflush=False,
            autocommit=False,
        )
    return _SESSIONMAKER_CACHE[db_path]
