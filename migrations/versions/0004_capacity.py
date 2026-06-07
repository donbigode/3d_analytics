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
    # TODO(W5 F2): typically adds settings.printer_hours_per_day (INT, default 22).
    pass


def downgrade() -> None:
    pass
