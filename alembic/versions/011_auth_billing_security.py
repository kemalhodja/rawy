"""auth verification and stripe fields

Revision ID: 011_auth_billing_security
Revises: 010_calendar_events
Create Date: 2026-03-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "011_auth_billing_security"
down_revision: Union[str, None] = "010_calendar_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _cols(table_name: str) -> set[str]:
    bind = op.get_bind()
    try:
        return {c["name"] for c in inspect(bind).get_columns(table_name)}
    except Exception:
        return set()


def upgrade() -> None:
    cols = _cols("users")
    if "is_superuser" not in cols:
        op.add_column("users", sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    if "is_verified" not in cols:
        op.add_column("users", sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    if "stripe_customer_id" not in cols:
        op.add_column("users", sa.Column("stripe_customer_id", sa.String(length=255), nullable=True))
    if "stripe_subscription_id" not in cols:
        op.add_column("users", sa.Column("stripe_subscription_id", sa.String(length=255), nullable=True))


def downgrade() -> None:
    cols = _cols("users")
    for c in ("stripe_subscription_id", "stripe_customer_id", "is_verified", "is_superuser"):
        if c in cols:
            op.drop_column("users", c)
