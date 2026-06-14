"""production_events table (com embedding/llm_tags p/ Fase B)

Revision ID: 0023_production_events
Revises: 0022_spool_color_mfr
Create Date: 2026-06-14 08:00:00.000000

Um registro por desfecho de produção (Concluir/Falhar). Inclui contexto por
peça (JSONB), grams_wasted na falha, e colunas embedding/llm_tags já criadas
mas nulas — preenchidas na Fase B (vetor + parsing LLM). Segue o padrão de
pgvector de 0006_llm_radar.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision: str = "0023_production_events"
down_revision: Union[str, Sequence[str], None] = "0022_spool_color_mfr"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "production_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("quote_id", UUID(as_uuid=True),
                  sa.ForeignKey("quotes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="1"),
        sa.Column("failure_description", sa.Text),
        sa.Column("context", JSONB),
        sa.Column("grams_wasted", sa.Numeric(10, 2)),
        sa.Column("llm_tags", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
    )
    op.execute("ALTER TABLE production_events ADD COLUMN embedding vector(384)")
    op.execute(
        "CREATE INDEX production_events_embedding_idx ON production_events "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )
    op.create_index("ix_production_events_quote_id", "production_events", ["quote_id"])
    op.create_index("ix_production_events_outcome", "production_events", ["outcome"])


def downgrade() -> None:
    op.drop_table("production_events")
