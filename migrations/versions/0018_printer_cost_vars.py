"""settings: printer cost variables (purchase price, life, maintenance)

Revision ID: 0018_printer_cost_vars
Revises: 0017_qi_filename_nullable
Create Date: 2026-06-09 14:00:00.000000

Adds the missing pieces of the production-cost formula:

* ``printer_purchase_price`` — sticker price of the machine. Just stored,
  but the UI uses it to derive ``printer_depreciation_per_hour`` if the
  user clicks the helper button.
* ``printer_useful_life_hours`` — total expected running hours, default
  7300 (small business: ~4h/day × 5 years).
* ``printer_maintenance_per_hour`` — wear-out budget separate from
  depreciation: nozzles, lubrication, belts, build plates. Added straight
  into ``compute_item_cost``.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0018_printer_cost_vars"
down_revision: Union[str, Sequence[str], None] = "0017_qi_filename_nullable"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "settings",
        sa.Column(
            "printer_purchase_price",
            sa.Numeric(10, 2),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "settings",
        sa.Column(
            "printer_useful_life_hours",
            sa.Integer(),
            nullable=False,
            server_default="7300",
        ),
    )
    op.add_column(
        "settings",
        sa.Column(
            "printer_maintenance_per_hour",
            sa.Numeric(10, 2),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("settings", "printer_maintenance_per_hour")
    op.drop_column("settings", "printer_useful_life_hours")
    op.drop_column("settings", "printer_purchase_price")
