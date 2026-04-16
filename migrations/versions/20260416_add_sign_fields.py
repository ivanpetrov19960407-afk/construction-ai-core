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


def upgrade() -> None:
    op.add_column("executive_docs", sa.Column("signed_at", sa.TIMESTAMP(), nullable=True))
    op.add_column("executive_docs", sa.Column("signed_by", sa.String(length=36), nullable=True))
    op.add_column("executive_docs", sa.Column("sig_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("executive_docs", "sig_url")
    op.drop_column("executive_docs", "signed_by")
    op.drop_column("executive_docs", "signed_at")
