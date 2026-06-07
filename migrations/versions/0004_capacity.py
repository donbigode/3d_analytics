"""capacity baseline (W5 F2)

Revision ID: 0004_capacity
Revises: 0003_calibration
Create Date: 2026-06-07 19:00:01.000000

Owned by Wave 5 Lane F2 (capacity forecast). Subagent fills in upgrade/downgrade.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql  # noqa: F401


revision: str = '0004_capacity'
down_revision: Union[str, Sequence[str], None] = '0003_calibration'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'settings',
        sa.Column(
            'printer_hours_per_day',
            sa.Integer(),
            nullable=False,
            server_default='22',
        ),
    )


def downgrade() -> None:
    op.drop_column('settings', 'printer_hours_per_day')
