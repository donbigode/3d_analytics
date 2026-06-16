"""contabil v2: sales.quote_kind, expenses.is_recurring, settings.revenue_tax_pct

Revision ID: 0026_contabil_v2
Revises: 0025_accounting
Create Date: 2026-06-16 10:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0026_contabil_v2"
down_revision: Union[str, Sequence[str], None] = "0025_accounting"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sales", sa.Column("quote_kind", sa.String(20), nullable=False,
                                     server_default="commercial"))
    op.add_column("expenses", sa.Column("is_recurring", sa.Boolean, nullable=False,
                                        server_default=sa.false()))
    op.add_column("settings", sa.Column("revenue_tax_pct", sa.Numeric(5, 2), nullable=False,
                                        server_default="0"))


def downgrade() -> None:
    op.drop_column("settings", "revenue_tax_pct")
    op.drop_column("expenses", "is_recurring")
    op.drop_column("sales", "quote_kind")
