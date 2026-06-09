"""quotes.retail_mode

Revision ID: 0016_quote_retail_mode
Revises: 0015_library_assets
Create Date: 2026-06-09 12:00:00.000000

When ``retail_mode`` is true, the customer-facing PDF hides the cost
breakdown (filament/time/material per item) and only shows quantity,
line total at the post-markup client price and the per-piece price.
Useful for retail sales where the owner doesn't want to expose internals.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0016_quote_retail_mode"
down_revision: Union[str, Sequence[str], None] = "0015_library_assets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "quotes",
        sa.Column(
            "retail_mode",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("quotes", "retail_mode")
