"""tabelas sales + expenses (aba Contábil)

Revision ID: 0025_accounting
Revises: 0024_production_suggestions
Create Date: 2026-06-15 09:00:00.000000

sales: linha materializada por orçamento comercial aprovado+. Campos-espelho
(quote_status/quote_total/cpv_calc/client_id) + editáveis preservados no sync.
expenses: despesas avulsas do DRE.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = "0025_accounting"
down_revision: Union[str, Sequence[str], None] = "0024_production_suggestions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sales",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("quote_id", UUID(as_uuid=True),
                  sa.ForeignKey("quotes.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("quote_status", sa.String(20), nullable=False),
        sa.Column("quote_total", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("cpv_calc", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("client_id", UUID(as_uuid=True),
                  sa.ForeignKey("clients.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_stale", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("is_sold", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("confirmed_revenue", sa.Numeric(10, 2), nullable=True),
        sa.Column("variable_costs", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("cpv_override", sa.Numeric(10, 2), nullable=True),
        sa.Column("sold_at", sa.Date, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_sales_sold_at", "sales", ["sold_at"])
    op.create_index("ix_sales_is_sold", "sales", ["is_sold"])

    op.create_table(
        "expenses",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("incurred_at", sa.Date, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_expenses_incurred_at", "expenses", ["incurred_at"])


def downgrade() -> None:
    op.drop_table("expenses")
    op.drop_table("sales")
