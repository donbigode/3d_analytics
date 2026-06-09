"""quote_items.filename nullable

Revision ID: 0017_qi_filename_nullable
Revises: 0016_quote_retail_mode
Create Date: 2026-06-09 13:00:00.000000

The gcode file becomes optional on quote items so users can record a
manually-priced piece without uploading anything. ``filename`` is left
empty in that case (NULL).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0017_qi_filename_nullable"
down_revision: Union[str, Sequence[str], None] = "0016_quote_retail_mode"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "quote_items",
        "filename",
        existing_type=sa.String(length=255),
        nullable=True,
    )


def downgrade() -> None:
    # Existing NULL rows would block the NOT NULL revert; fill with empty.
    op.execute("UPDATE quote_items SET filename = '' WHERE filename IS NULL")
    op.alter_column(
        "quote_items",
        "filename",
        existing_type=sa.String(length=255),
        nullable=False,
    )
