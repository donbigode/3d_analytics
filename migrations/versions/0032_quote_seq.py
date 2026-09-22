"""quotes.seq — número humano do orçamento (#0042)

Backfill cronológico: numera o histórico existente por created_at, com o
id como desempate determinístico. A sequence assume dali em diante.

A coluna nasce com DEFAULT, então uma API da versão anterior continua
inserindo orçamentos sem erro — a migração pode subir antes do deploy.

Revision ID: 0032_quote_seq
Revises: 0031_printer_job_spool
Create Date: 2026-09-21 10:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0032_quote_seq"
down_revision: Union[str, Sequence[str], None] = "0031_printer_job_spool"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("quotes", sa.Column("seq", sa.Integer(), nullable=True))
    op.execute("CREATE SEQUENCE quote_seq")
    op.execute(
        """
        WITH ord AS (
            SELECT id, row_number() OVER (ORDER BY created_at, id) AS rn FROM quotes
        )
        UPDATE quotes q SET seq = ord.rn FROM ord WHERE q.id = ord.id
        """
    )
    op.execute(
        "SELECT setval('quote_seq', COALESCE((SELECT MAX(seq) FROM quotes), 0) + 1, false)"
    )
    op.alter_column("quotes", "seq", nullable=False,
                    server_default=sa.text("nextval('quote_seq')"))
    op.create_index("ix_quotes_seq", "quotes", ["seq"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_quotes_seq", table_name="quotes")
    op.drop_column("quotes", "seq")
    op.execute("DROP SEQUENCE IF EXISTS quote_seq")
