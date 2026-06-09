"""settings.digest_auto_enabled

Revision ID: 0019_digest_auto_toggle
Revises: 0018_printer_cost_vars
Create Date: 2026-06-09 15:00:00.000000

Toggle for the daily LLM digest. When true (default) the dashboard
auto-loads/regenerates the digest once per day; when false, the digest
is only generated when the user clicks "atualizar" manually.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0019_digest_auto_toggle"
down_revision: Union[str, Sequence[str], None] = "0018_printer_cost_vars"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "settings",
        sa.Column(
            "digest_auto_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column("settings", "digest_auto_enabled")
