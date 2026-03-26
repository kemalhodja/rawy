"""Aktif odak oturumu: users.active_focus_block_id

Revision ID: 007_active_focus
Revises: 006_task_flow_simple
Create Date: 2026-03-26

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007_active_focus"
down_revision: Union[str, None] = "006_task_flow_simple"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("active_focus_block_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_users_active_focus_block",
        "users",
        "focus_blocks",
        ["active_focus_block_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_users_active_focus_block", "users", type_="foreignkey")
    op.drop_column("users", "active_focus_block_id")
