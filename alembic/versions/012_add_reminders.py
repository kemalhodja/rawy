"""Add reminders table

Revision ID: 012
Revises: 011_auth_billing_security
Create Date: 2026-03-28 00:55:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '012'
down_revision: Union[str, None] = '011_auth_billing_security'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite batch mode için
    with op.batch_alter_table('reminders', schema=None) as batch_op:
        pass
    
    # Reminders tablosunu oluştur (batch mode ile)
    op.create_table(
        'reminders',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('remind_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('timezone', sa.String(length=64), nullable=False, server_default='UTC'),
        sa.Column('recurrence', sa.String(length=20), nullable=True),
        sa.Column('recurrence_count', sa.Integer(), nullable=True),
        sa.Column('is_triggered', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('is_dismissed', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('is_snoozed', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('snooze_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notify_methods', sa.JSON(), nullable=True),
        sa.Column('source_voice_note_id', sa.Integer(), nullable=True),
        sa.Column('linked_task_id', sa.Integer(), nullable=True),
        sa.Column('trigger_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_triggered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Indexes
    op.create_index(op.f('ix_reminders_user_id'), 'reminders', ['user_id'], unique=False)
    op.create_index(op.f('ix_reminders_remind_at'), 'reminders', ['remind_at'], unique=False)


def downgrade() -> None:
    op.drop_table('reminders')
