"""add calendar_events table

Revision ID: 010_calendar_events
Revises: 009_review_capsule_companion
Create Date: 2026-03-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "010_calendar_events"
down_revision: Union[str, None] = "009_review_capsule_companion"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    try:
        return inspect(bind).has_table(table_name)
    except Exception:
        return False


def upgrade() -> None:
    if _has_table("calendar_events"):
        return

    op.create_table(
        "calendar_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_note_id", sa.Integer(), nullable=True),
        sa.Column("is_focus_block", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("external_event_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["source_note_id"], ["voice_notes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_calendar_events_user_id", "calendar_events", ["user_id"], unique=False)


def downgrade() -> None:
    if not _has_table("calendar_events"):
        return
    op.drop_index("ix_calendar_events_user_id", table_name="calendar_events")
    op.drop_table("calendar_events")
