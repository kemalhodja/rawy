"""Add speaker recognition tables

Revision ID: 013
Revises: 012
Create Date: 2026-03-28 03:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '013'
down_revision: Union[str, None] = '012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Voice Embeddings
    op.create_table(
        'voice_embeddings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('embedding_vector', sa.JSON(), nullable=False),
        sa.Column('embedding_model', sa.String(length=50), nullable=False, server_default='ecapa_tdnn'),
        sa.Column('source_voice_note_id', sa.Integer(), nullable=True),
        sa.Column('sample_duration', sa.Float(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('confidence_score', sa.Float(), nullable=True),
        sa.Column('speaker_label', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_voice_embeddings_user_id'), 'voice_embeddings', ['user_id'], unique=False)
    op.create_foreign_key(None, 'voice_embeddings', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key(None, 'voice_embeddings', 'voice_notes', ['source_voice_note_id'], ['id'], ondelete='SET NULL')
    
    # Speaker Segments
    op.create_table(
        'speaker_segments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('voice_note_id', sa.Integer(), nullable=False),
        sa.Column('start_time', sa.Float(), nullable=False),
        sa.Column('end_time', sa.Float(), nullable=False),
        sa.Column('speaker_id', sa.Integer(), nullable=True),
        sa.Column('speaker_label', sa.String(length=100), nullable=True),
        sa.Column('transcript', sa.Text(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_speaker_segments_voice_note_id'), 'speaker_segments', ['voice_note_id'], unique=False)
    op.create_foreign_key(None, 'speaker_segments', 'voice_notes', ['voice_note_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key(None, 'speaker_segments', 'voice_embeddings', ['speaker_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    op.drop_table('speaker_segments')
    op.drop_table('voice_embeddings')
