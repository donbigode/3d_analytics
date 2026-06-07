"""calibration baseline (W5 F1)

Revision ID: 0003_calibration
Revises: 0002_qi_material_nullable
Create Date: 2026-06-07 19:00:00.000000

Owned by Wave 5 Lane F1 (auto-calibration). Subagent fills in upgrade/downgrade.
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
    # TODO(W5 F1): create calibration_insights table (or whatever shape the lane decides)
    pass


def downgrade() -> None:
    pass
