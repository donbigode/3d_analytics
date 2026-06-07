"""trends baseline (W5 F3)

Revision ID: 0005_trends
Revises: 0004_capacity
Create Date: 2026-06-07 19:00:02.000000

Owned by Wave 5 Lane F3 (trend radar). Subagent fills in upgrade/downgrade.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql  # noqa: F401


revision: str = '0005_trends'
down_revision: Union[str, Sequence[str], None] = '0004_capacity'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # TODO(W5 F3): create keyword_ideas + keyword_observations tables.
    pass


def downgrade() -> None:
    pass
