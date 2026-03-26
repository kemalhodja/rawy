"""Deneme süresi ve faturalama alanları

Revision ID: 008_monetization
Revises: 007_active_focus
Create Date: 2026-03-26

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008_monetization"
down_revision: Union[str, None] = "007_active_focus"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("billing_interval", sa.String(length=16), nullable=True),
    )
    op.execute("UPDATE users SET plan = 'starter' WHERE plan = 'free' OR plan IS NULL")


def downgrade() -> None:
    op.execute("UPDATE users SET plan = 'free' WHERE plan = 'starter'")
    op.drop_column("users", "billing_interval")
    op.drop_column("users", "trial_ends_at")
