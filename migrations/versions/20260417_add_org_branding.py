"""create org_branding table

Revision ID: 20260417_add_org_branding
Revises: 20260417_add_org_subscriptions
Create Date: 2026-04-17
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20260417_add_org_branding"
down_revision = "20260417_add_org_subscriptions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "org_branding",
        sa.Column("org_id", sa.Text(), nullable=False),
        sa.Column("company_name", sa.Text(), nullable=False, server_default="Construction AI"),
        sa.Column("logo_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("primary_color", sa.Text(), nullable=False, server_default="#2563eb"),
        sa.Column("accent_color", sa.Text(), nullable=False, server_default="#1d4ed8"),
        sa.Column("favicon_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("custom_domain", sa.Text(), nullable=False, server_default=""),
        sa.Column("support_email", sa.Text(), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("org_id"),
    )


def downgrade() -> None:
    op.drop_table("org_branding")
