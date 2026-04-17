"""create org_subscriptions table

Revision ID: 20260417_add_org_subscriptions
Revises: 20260417_add_org_id
Create Date: 2026-04-17
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20260417_add_org_subscriptions"
down_revision = "20260417_add_org_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "org_subscriptions",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("org_id", sa.Text(), nullable=False),
        sa.Column("plan", sa.Text(), nullable=False),
        sa.Column("valid_until", sa.Text(), nullable=True),
        sa.Column("payment_id", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.Text(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_org_subscriptions_org_id", "org_subscriptions", ["org_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_org_subscriptions_org_id", table_name="org_subscriptions")
    op.drop_table("org_subscriptions")
