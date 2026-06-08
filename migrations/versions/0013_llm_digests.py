"""llm_digests cache table

Revision ID: 0013_llm_digests
Revises: 0012_model_source
Create Date: 2026-06-08 14:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0013_llm_digests"
down_revision: Union[str, Sequence[str], None] = "0012_model_source"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llm_digests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("digest_date", sa.Date(), nullable=False, unique=True),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_llm_digests_date", "llm_digests", ["digest_date"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_llm_digests_date", table_name="llm_digests")
    op.drop_table("llm_digests")
