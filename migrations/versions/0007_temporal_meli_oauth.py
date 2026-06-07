"""temporal_window on suggestions + keyword_ideas; mercadolivre OAuth creds.

Revision ID: 0007_temporal_meli
Revises: 0006_llm_radar
Create Date: 2026-06-07 23:00:00.000000

Adds:
  - keyword_ideas.temporal_window VARCHAR(10) DEFAULT 'week'
  - llm_suggestions.temporal_window VARCHAR(10) DEFAULT 'week'
  - settings.meli_app_id, meli_client_secret, meli_access_token,
    meli_token_expires_at (Mercado Livre OAuth client_credentials).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007_temporal_meli"
down_revision: Union[str, Sequence[str], None] = "0006_llm_radar"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "keyword_ideas",
        sa.Column("temporal_window", sa.String(length=10), nullable=False, server_default="week"),
    )
    op.add_column(
        "llm_suggestions",
        sa.Column("temporal_window", sa.String(length=10), nullable=False, server_default="week"),
    )
    op.add_column("settings", sa.Column("meli_app_id", sa.String(length=80), nullable=True))
    op.add_column("settings", sa.Column("meli_client_secret", sa.String(length=200), nullable=True))
    op.add_column("settings", sa.Column("meli_access_token", sa.String(length=400), nullable=True))
    op.add_column("settings", sa.Column("meli_token_expires_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("settings", "meli_token_expires_at")
    op.drop_column("settings", "meli_access_token")
    op.drop_column("settings", "meli_client_secret")
    op.drop_column("settings", "meli_app_id")
    op.drop_column("llm_suggestions", "temporal_window")
    op.drop_column("keyword_ideas", "temporal_window")
