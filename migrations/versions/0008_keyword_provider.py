"""keyword_ideas.source_provider

Revision ID: 0008_kw_provider
Revises: 0007_temporal_meli
Create Date: 2026-06-07 23:30:00.000000

Tracks where each keyword idea came from: NULL = manual; 'anthropic' or
'gemini' when promoted from an LLMSuggestion. Surfaced as a badge on the
trends page.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008_kw_provider"
down_revision: Union[str, Sequence[str], None] = "0007_temporal_meli"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "keyword_ideas",
        sa.Column("source_provider", sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("keyword_ideas", "source_provider")
