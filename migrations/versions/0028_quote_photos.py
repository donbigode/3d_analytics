"""quote_photos (fotos no orçamento)

Revision ID: 0028_quote_photos
Revises: 0027_export_config
Create Date: 2026-06-18 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = "0028_quote_photos"
down_revision: Union[str, Sequence[str], None] = "0027_export_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "quote_photos",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("quote_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("quotes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("quote_item_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("quote_items.id", ondelete="CASCADE"), nullable=True),
        sa.Column("storage_path", sa.String(500), nullable=False),
        sa.Column("content_type", sa.String(40), nullable=False, server_default="image/jpeg"),
        sa.Column("size_bytes", sa.Integer, nullable=False, server_default="0"),
        sa.Column("width", sa.Integer, nullable=False, server_default="0"),
        sa.Column("height", sa.Integer, nullable=False, server_default="0"),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_quote_photos_quote_id", "quote_photos", ["quote_id"])
    op.create_index("ix_quote_photos_quote_item_id", "quote_photos", ["quote_item_id"])


def downgrade() -> None:
    op.drop_table("quote_photos")
