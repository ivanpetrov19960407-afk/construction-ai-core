"""add sign fields to executive_docs

Revision ID: 20260416_add_sign_fields
Revises:
Create Date: 2026-04-16
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20260416_add_sign_fields"
down_revision = None
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "executive_docs" not in inspector.get_table_names():
        op.create_table(
            "executive_docs",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _has_column("executive_docs", "signed_at"):
        op.add_column("executive_docs", sa.Column("signed_at", sa.TIMESTAMP(), nullable=True))
    if not _has_column("executive_docs", "signed_by"):
        op.add_column("executive_docs", sa.Column("signed_by", sa.String(length=36), nullable=True))
    if not _has_column("executive_docs", "sig_url"):
        op.add_column("executive_docs", sa.Column("sig_url", sa.Text(), nullable=True))


def downgrade() -> None:
    if _has_column("executive_docs", "sig_url"):
        op.drop_column("executive_docs", "sig_url")
    if _has_column("executive_docs", "signed_by"):
        op.drop_column("executive_docs", "signed_by")
    if _has_column("executive_docs", "signed_at"):
        op.drop_column("executive_docs", "signed_at")
