"""add org_id multitenancy columns

Revision ID: 20260417_add_org_id
Revises: 20260416_create_isup_submissions
Create Date: 2026-04-17
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20260417_add_org_id"
down_revision = "20260416_create_isup_submissions"
branch_labels = None
depends_on = None


_TABLES = (
    "projects",
    "executive_docs",
    "kg_entries",
    "generated_docs",
    "isup_submissions",
)


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column("org_id", sa.Text(), nullable=False, server_default="default"),
        )
        op.create_index(f"ix_{table}_org_id", table, ["org_id"], unique=False)

    op.add_column(
        "users",
        sa.Column("org_id", sa.Text(), nullable=False, server_default="default"),
    )
    op.create_index("ix_users_org_id", "users", ["org_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_users_org_id", table_name="users")
    op.drop_column("users", "org_id")

    for table in reversed(_TABLES):
        op.drop_index(f"ix_{table}_org_id", table_name=table)
        op.drop_column(table, "org_id")
