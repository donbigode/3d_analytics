"""production_suggestions cache table

Revision ID: 0024_production_suggestions
Revises: 0023_production_events
Create Date: 2026-06-14 14:00:00.000000

Cache da última geração de sugestões de IA da produção (padrão LLMDigest).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision: str = "0024_production_suggestions"
down_revision: Union[str, Sequence[str], None] = "0023_production_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "production_suggestions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("body", JSONB, nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("source_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("generated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("production_suggestions")
