"""add short_id to projects

Revision ID: 20260419_add_short_id_to_projects
Revises: 20260417_add_push_subscriptions
Create Date: 2026-04-19
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20260419_add_short_id_to_projects"
down_revision = "20260417_add_push_subscriptions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("short_id", sa.BigInteger(), nullable=True),
    )

    bind = op.get_bind()
    bind.execute(sa.text("UPDATE projects SET short_id = rowid WHERE short_id IS NULL"))

    op.create_unique_constraint("uq_projects_short_id", "projects", ["short_id"])
    op.create_index("ix_projects_short_id", "projects", ["short_id"], unique=False)
    op.alter_column("projects", "short_id", nullable=False)

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS project_short_id_seq (
            id INTEGER PRIMARY KEY AUTOINCREMENT
        )
        """
    )
    max_short_id = bind.execute(sa.text("SELECT COALESCE(MAX(short_id), 0) FROM projects")).scalar()
    if int(max_short_id or 0) > 0:
        bind.execute(
            sa.text("INSERT INTO project_short_id_seq (id) VALUES (:short_id)"),
            {"short_id": int(max_short_id)},
        )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS project_short_id_seq")
    op.drop_index("ix_projects_short_id", table_name="projects")
    op.drop_constraint("uq_projects_short_id", "projects", type_="unique")
    op.drop_column("projects", "short_id")
