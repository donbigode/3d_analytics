"""settings.youtube_api_key

Revision ID: 0011_youtube_key
Revises: 0010_reddit_oauth
Create Date: 2026-06-08 01:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0011_youtube_key"
down_revision: Union[str, Sequence[str], None] = "0010_reddit_oauth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("settings", sa.Column("youtube_api_key", sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column("settings", "youtube_api_key")
