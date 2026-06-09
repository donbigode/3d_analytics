"""material_versions waste rates + quote_items multi_color flag

Revision ID: 0020_material_waste
Revises: 0019_digest_auto_toggle
Create Date: 2026-06-09 16:00:00.000000

Refugo: the share of filament that ends up as purges, brims, supports
and color-change towers. Modelled per material × (single-color vs
multi-color). Per-item flag ``is_multi_color`` picks which one to apply.

Defaults (in percent of declared filament length):
  - single_color_waste_pct = 2   (skirt + brim + first-layer purge)
  - multi_color_waste_pct  = 20  (purge/wipe tower per color change)

These are conservative starting points — the user tunes them per material
in the materials editor.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0020_material_waste"
down_revision: Union[str, Sequence[str], None] = "0019_digest_auto_toggle"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "material_versions",
        sa.Column(
            "single_color_waste_pct",
            sa.Numeric(5, 2),
            nullable=False,
            server_default="2.00",
        ),
    )
    op.add_column(
        "material_versions",
        sa.Column(
            "multi_color_waste_pct",
            sa.Numeric(5, 2),
            nullable=False,
            server_default="20.00",
        ),
    )
    op.add_column(
        "quote_items",
        sa.Column(
            "is_multi_color",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("quote_items", "is_multi_color")
    op.drop_column("material_versions", "multi_color_waste_pct")
    op.drop_column("material_versions", "single_color_waste_pct")
