"""calibration baseline (W5 F1)

Revision ID: 0003_calibration
Revises: 0002_qi_material_nullable
Create Date: 2026-06-07 19:00:00.000000

Creates the `calibration_insights` table that stores suggestions surfaced by
comparing real consumption (MaterialConsumption) against declared values
(QuoteItem.gcode_meta) and the catalog reference (MaterialVersion).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql  # noqa: F401


revision: str = '0003_calibration'
down_revision: Union[str, Sequence[str], None] = '0002_qi_material_nullable'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'calibration_insights',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('scope_kind', sa.String(length=40), nullable=False),
        sa.Column('scope_ref', sa.String(length=80), nullable=False),
        sa.Column('observed_value', sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column('current_value', sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column('suggested_value', sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column('delta_pct', sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column('sample_size', sa.Integer(), nullable=False),
        sa.Column('computed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='open'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_calibration_insights_status',
        'calibration_insights',
        ['status'],
        unique=False,
    )
    op.create_index(
        'ix_calibration_insights_scope',
        'calibration_insights',
        ['scope_kind', 'scope_ref'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_calibration_insights_scope', table_name='calibration_insights')
    op.drop_index('ix_calibration_insights_status', table_name='calibration_insights')
    op.drop_table('calibration_insights')
