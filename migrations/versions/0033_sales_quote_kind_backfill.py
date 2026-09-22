"""Backfill de sales.quote_kind

quote_kind nasceu com server_default 'commercial' e só é reescrito por
sync_sales(), que ignora orçamentos fora dos status ativos. Logo, linhas
arquivadas (is_stale) de orçamentos PESSOAIS criadas antes da coluna
ficaram marcadas como comerciais — e apareceriam na aba errada.

Só dados, sem schema. Idempotente. downgrade é no-op: não há como saber
quais linhas foram tocadas, e restaurar um valor sabidamente errado não
serve a ninguém.

Revision ID: 0033_sales_quote_kind_backfill
Revises: 0032_quote_seq
Create Date: 2026-09-21 11:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0033_sales_quote_kind_backfill"
down_revision: Union[str, Sequence[str], None] = "0032_quote_seq"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE sales s
           SET quote_kind = q.kind
          FROM quotes q
         WHERE q.id = s.quote_id
           AND s.quote_kind IS DISTINCT FROM q.kind
        """
    )


def downgrade() -> None:
    """No-op — ver docstring do módulo."""
