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

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "generated_docs" in inspector.get_table_names():
        generated_docs_columns = {
            column["name"] for column in inspector.get_columns("generated_docs")
        }
        op.execute(
            """
            CREATE TABLE generated_docs_new (
                id TEXT NOT NULL,
                type TEXT NOT NULL,
                org_id TEXT NOT NULL DEFAULT 'default',
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (id, type, org_id)
            )
            """
        )
        if "org_id" in generated_docs_columns:
            op.execute(
                """
                INSERT INTO generated_docs_new (id, type, org_id, payload, created_at, updated_at)
                SELECT
                    id,
                    type,
                    COALESCE(org_id, 'default') AS org_id,
                    payload,
                    created_at,
                    updated_at
                FROM generated_docs
                """
            )
        else:
            op.execute(
                """
                INSERT INTO generated_docs_new (id, type, org_id, payload, created_at, updated_at)
                SELECT
                    id,
                    type,
                    'default' AS org_id,
                    payload,
                    created_at,
                    updated_at
                FROM generated_docs
                """
            )
        op.drop_table("generated_docs")
        op.rename_table("generated_docs_new", "generated_docs")
        op.create_index("ix_generated_docs_org_id", "generated_docs", ["org_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "generated_docs" in inspector.get_table_names():
        op.execute(
            """
            CREATE TABLE generated_docs_old (
                id TEXT NOT NULL,
                type TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (id, type)
            )
            """
        )
        op.execute(
            """
            INSERT INTO generated_docs_old (id, type, payload, created_at, updated_at)
            WITH ranked AS (
                SELECT
                    id,
                    type,
                    payload,
                    created_at,
                    updated_at,
                    ROW_NUMBER() OVER (
                        PARTITION BY id, type
                        ORDER BY updated_at DESC, created_at DESC, org_id ASC
                    ) AS rn
                FROM generated_docs
            )
            SELECT id, type, payload, created_at, updated_at
            FROM ranked
            WHERE rn = 1
            """
        )
        op.drop_table("generated_docs")
        op.rename_table("generated_docs_old", "generated_docs")

    op.drop_index("ix_users_org_id", table_name="users")
    op.drop_column("users", "org_id")

    for table in reversed(_TABLES):
        op.drop_index(f"ix_{table}_org_id", table_name=table)
        op.drop_column(table, "org_id")
