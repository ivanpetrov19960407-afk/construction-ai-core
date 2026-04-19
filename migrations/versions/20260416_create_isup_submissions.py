"""create isup_submissions table

Revision ID: 20260416_create_isup_submissions
Revises: 20260416_add_sign_fields
Create Date: 2026-04-16
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20260416_create_isup_submissions"
down_revision = "20260416_add_sign_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "postgresql":
        id_type: sa.TypeEngine = sa.UUID()
        json_type: sa.TypeEngine = sa.JSON()
    else:
        id_type = sa.String(length=36)
        json_type = sa.JSON()

    op.create_table(
        "isup_submissions",
        sa.Column("id", id_type, nullable=False),
        sa.Column("project_id", id_type, nullable=False),
        sa.Column("doc_id", id_type, nullable=False),
        sa.Column("submission_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("submitted_at", sa.TIMESTAMP(timezone=False), nullable=False),
        sa.Column("response_json", json_type, nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_isup_submissions_submission_id",
        "isup_submissions",
        ["submission_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_isup_submissions_submission_id", table_name="isup_submissions")
    op.drop_table("isup_submissions")
