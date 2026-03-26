"""tasks + voice pipeline alanları

Revision ID: 003_intent_pipeline
Revises: 002_focus_calendar
Create Date: 2026-03-26

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_intent_pipeline"
down_revision: Union[str, None] = "002_focus_calendar"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    created_default = sa.text("now()") if not is_sqlite else sa.text("CURRENT_TIMESTAMP")
    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("done", sa.Boolean(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_voice_note_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=created_default, nullable=True),
        sa.ForeignKeyConstraint(["source_voice_note_id"], ["voice_notes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.add_column("voice_notes", sa.Column("ai_category", sa.String(length=32), nullable=True))
    op.add_column("voice_notes", sa.Column("linked_task_id", sa.Integer(), nullable=True))
    op.add_column("voice_notes", sa.Column("linked_focus_block_id", sa.Integer(), nullable=True))
    op.add_column("voice_notes", sa.Column("pipeline_error", sa.Text(), nullable=True))
    if not is_sqlite:
        op.create_foreign_key(
            "voice_notes_linked_task_id_fkey",
            "voice_notes",
            "tasks",
            ["linked_task_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_foreign_key(
            "voice_notes_linked_focus_block_id_fkey",
            "voice_notes",
            "focus_blocks",
            ["linked_focus_block_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.add_column("focus_blocks", sa.Column("source_voice_note_id", sa.Integer(), nullable=True))
    if not is_sqlite:
        op.create_foreign_key(
            "focus_blocks_source_voice_note_id_fkey",
            "focus_blocks",
            "voice_notes",
            ["source_voice_note_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    if not is_sqlite:
        op.drop_constraint("focus_blocks_source_voice_note_id_fkey", "focus_blocks", type_="foreignkey")
    op.drop_column("focus_blocks", "source_voice_note_id")
    if not is_sqlite:
        op.drop_constraint("voice_notes_linked_focus_block_id_fkey", "voice_notes", type_="foreignkey")
        op.drop_constraint("voice_notes_linked_task_id_fkey", "voice_notes", type_="foreignkey")
    op.drop_column("voice_notes", "pipeline_error")
    op.drop_column("voice_notes", "linked_focus_block_id")
    op.drop_column("voice_notes", "linked_task_id")
    op.drop_column("voice_notes", "ai_category")
    op.drop_table("tasks")
