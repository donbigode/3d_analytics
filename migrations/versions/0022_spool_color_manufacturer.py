"""spools color + manufacturer

Revision ID: 0022_spool_color_mfr
Revises: 0021_must_change_password
Create Date: 2026-06-13 22:00:00.000000

A physical spool is a concrete material+color+manufacturer bought at a
point in time. We already denormalize ``material_type`` onto the spool;
``color`` and ``manufacturer`` follow the same snapshot pattern so the
stock table can display them (the catalog material's color is otherwise
lost at purchase time). Both nullable — existing spools simply have none.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0022_spool_color_mfr"
down_revision: Union[str, Sequence[str], None] = "0021_must_change_password"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("spools", sa.Column("color", sa.String(60), nullable=True))
    op.add_column("spools", sa.Column("manufacturer", sa.String(120), nullable=True))


def downgrade() -> None:
    op.drop_column("spools", "manufacturer")
    op.drop_column("spools", "color")
