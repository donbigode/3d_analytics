"""reddit oauth columns

Revision ID: 0010_reddit_oauth
Revises: 0009_openai_key
Create Date: 2026-06-08 00:30:00.000000

Reddit closed the anonymous /search.json endpoint in 2024-2025. To query it
from the radar you need a registered "script" app at reddit.com/prefs/apps.
This migration stores the client_id/secret + cached access_token, mirroring
the Mercado Livre OAuth columns.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0010_reddit_oauth"
down_revision: Union[str, Sequence[str], None] = "0009_openai_key"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("settings", sa.Column("reddit_client_id", sa.String(length=80), nullable=True))
    op.add_column("settings", sa.Column("reddit_client_secret", sa.String(length=200), nullable=True))
    op.add_column("settings", sa.Column("reddit_access_token", sa.String(length=400), nullable=True))
    op.add_column(
        "settings",
        sa.Column("reddit_token_expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("settings", "reddit_token_expires_at")
    op.drop_column("settings", "reddit_access_token")
    op.drop_column("settings", "reddit_client_secret")
    op.drop_column("settings", "reddit_client_id")
