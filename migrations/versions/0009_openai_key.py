"""settings.openai_api_key

Revision ID: 0009_openai_key
Revises: 0008_kw_provider
Create Date: 2026-06-07 23:55:00.000000

Adds a slot for the OpenAI API key on the singleton Settings row so the
trend radar can fall back to GPT when Anthropic/Gemini are exhausted.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0009_openai_key"
down_revision: Union[str, Sequence[str], None] = "0008_kw_provider"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "settings",
        sa.Column("openai_api_key", sa.String(length=200), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("settings", "openai_api_key")
