"""Kayıt türleri: toplantı, yürüyüş, yansıma alanları

Revision ID: 004_recording_types
Revises: 003_intent_pipeline
Create Date: 2026-03-26

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004_recording_types"
down_revision: Union[str, None] = "003_intent_pipeline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "voice_notes",
        sa.Column("recording_type", sa.String(length=32), server_default="quick_note", nullable=False),
    )
    op.add_column("voice_notes", sa.Column("meeting_summary", sa.Text(), nullable=True))
    op.add_column(
        "voice_notes",
        sa.Column("meeting_action_items", postgresql.JSON(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "voice_notes",
        sa.Column("related_note_ids", postgresql.ARRAY(sa.Integer()), nullable=True),
    )
    op.add_column("voice_notes", sa.Column("mood_score", sa.Float(), nullable=True))
    op.add_column("voice_notes", sa.Column("reflection_patterns", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("voice_notes", "reflection_patterns")
    op.drop_column("voice_notes", "mood_score")
    op.drop_column("voice_notes", "related_note_ids")
    op.drop_column("voice_notes", "meeting_action_items")
    op.drop_column("voice_notes", "meeting_summary")
    op.drop_column("voice_notes", "recording_type")
