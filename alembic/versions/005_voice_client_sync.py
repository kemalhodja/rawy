"""Çevrimdışı senkron client_id, transkript dili, hızlı kayıt uyarısı

Revision ID: 005_voice_client_sync
Revises: 004_recording_types
Create Date: 2026-03-26

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005_voice_client_sync"
down_revision: Union[str, None] = "004_recording_types"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"
    op.add_column("voice_notes", sa.Column("client_id", sa.String(length=64), nullable=True))
    op.add_column(
        "voice_notes",
        sa.Column("client_recorded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("voice_notes", sa.Column("requested_language", sa.String(length=16), nullable=True))
    op.add_column(
        "voice_notes",
        sa.Column("quick_capture_exceeded", sa.Boolean(), nullable=False, server_default="false"),
    )
    if is_pg:
        op.create_index(
            "ix_voice_notes_user_client_id",
            "voice_notes",
            ["user_id", "client_id"],
            unique=True,
            postgresql_where=sa.text("client_id IS NOT NULL"),
        )
    else:
        op.create_index(
            "ix_voice_notes_user_client_id",
            "voice_notes",
            ["user_id", "client_id"],
            unique=True,
        )


def downgrade() -> None:
    op.drop_index("ix_voice_notes_user_client_id", table_name="voice_notes")
    op.drop_column("voice_notes", "quick_capture_exceeded")
    op.drop_column("voice_notes", "requested_language")
    op.drop_column("voice_notes", "client_recorded_at")
    op.drop_column("voice_notes", "client_id")
