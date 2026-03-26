"""Görev akışı: derin/yüzeysel, erteleme, yoklama soğuması

Revision ID: 006_task_flow_simple
Revises: 005_voice_client_sync
Create Date: 2026-03-26

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006_task_flow_simple"
down_revision: Union[str, None] = "005_voice_client_sync"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("depth", sa.String(length=16), server_default="shallow", nullable=False),
    )
    op.add_column("tasks", sa.Column("snooze_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("last_task_nudge_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "last_task_nudge_at")
    op.drop_column("tasks", "snooze_until")
    op.drop_column("tasks", "depth")
