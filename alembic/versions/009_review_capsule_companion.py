"""review/capsule fields and focus companion sessions

Revision ID: 009_review_capsule_companion
Revises: 008_monetization
Create Date: 2026-03-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "009_review_capsule_companion"
down_revision: Union[str, None] = "008_monetization"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _cols(table_name: str) -> set[str]:
    bind = op.get_bind()
    try:
        return {c["name"] for c in inspect(bind).get_columns(table_name)}
    except Exception:
        return set()


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    try:
        return inspect(bind).has_table(table_name)
    except Exception:
        return False


def upgrade() -> None:
    cols = _cols("voice_notes")
    if "task_converted" not in cols:
        op.add_column("voice_notes", sa.Column("task_converted", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    if "review_at" not in cols:
        op.add_column("voice_notes", sa.Column("review_at", sa.DateTime(timezone=True), nullable=True))
    if "review_status" not in cols:
        op.add_column("voice_notes", sa.Column("review_status", sa.String(length=20), nullable=False, server_default="none"))
    if "capsule_at" not in cols:
        op.add_column("voice_notes", sa.Column("capsule_at", sa.DateTime(timezone=True), nullable=True))
    if "capsule_message" not in cols:
        op.add_column("voice_notes", sa.Column("capsule_message", sa.Text(), nullable=True))
    if "capsule_delivered_at" not in cols:
        op.add_column("voice_notes", sa.Column("capsule_delivered_at", sa.DateTime(timezone=True), nullable=True))

    if not _has_table("focus_sessions"):
        op.create_table(
            "focus_sessions",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("host_user_id", sa.Integer(), nullable=False),
            sa.Column("partner_user_id", sa.Integer(), nullable=True),
            sa.Column("mode", sa.String(length=20), nullable=False, server_default="solo"),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("checkin_note", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["host_user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["partner_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_focus_sessions_host_user_id", "focus_sessions", ["host_user_id"], unique=False)
        op.create_index("ix_focus_sessions_partner_user_id", "focus_sessions", ["partner_user_id"], unique=False)


def downgrade() -> None:
    if _has_table("focus_sessions"):
        op.drop_index("ix_focus_sessions_partner_user_id", table_name="focus_sessions")
        op.drop_index("ix_focus_sessions_host_user_id", table_name="focus_sessions")
        op.drop_table("focus_sessions")

    cols = _cols("voice_notes")
    for col in ("capsule_delivered_at", "capsule_message", "capsule_at", "review_status", "review_at", "task_converted"):
        if col in cols:
            op.drop_column("voice_notes", col)
