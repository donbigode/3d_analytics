"""trends baseline (W5 F3)

Revision ID: 0005_trends
Revises: 0004_capacity
Create Date: 2026-06-07 19:00:02.000000

Creates keyword_ideas + keyword_observations tables. Daily observations track
google_trends interest scores and mercadolivre volume/price for each idea.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0005_trends'
down_revision: Union[str, Sequence[str], None] = '0004_capacity'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'keyword_ideas',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('term', sa.String(length=120), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('term', name='uq_keyword_ideas_term'),
    )
    op.create_table(
        'keyword_observations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('keyword_id', sa.UUID(), nullable=False),
        sa.Column('source', sa.String(length=40), nullable=False),
        sa.Column('metric', sa.String(length=40), nullable=False),
        sa.Column('value', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('raw_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            'taken_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['keyword_id'], ['keyword_ideas.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_keyword_observations_keyword_taken',
        'keyword_observations',
        ['keyword_id', 'taken_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        'ix_keyword_observations_keyword_taken', table_name='keyword_observations'
    )
    op.drop_table('keyword_observations')
    op.drop_table('keyword_ideas')
