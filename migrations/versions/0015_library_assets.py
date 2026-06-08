"""library.assets + quote_items.asset_id

Revision ID: 0015_library_assets
Revises: 0014_mat_type_color
Create Date: 2026-06-08 20:00:00.000000

Local library of 3D-printing files (.gcode, .3mf, .stl). Deduplicated by
SHA-256. quote_items gets an optional asset_id so quotes can reference an
existing asset instead of re-uploading the same file.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0015_library_assets"
down_revision: Union[str, Sequence[str], None] = "0014_mat_type_color"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("format", sa.String(length=10), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("file_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("storage_path", sa.String(length=500), nullable=False),
        sa.Column("parsed_meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source_url", sa.String(length=800), nullable=True),
        sa.Column("source_site", sa.String(length=60), nullable=True),
        sa.Column("source_author", sa.String(length=200), nullable=True),
        sa.Column("source_license", sa.String(length=80), nullable=True),
        sa.Column("thumbnail_url", sa.String(length=800), nullable=True),
        sa.Column("tags", postgresql.ARRAY(sa.String(length=40)), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_assets_format", "assets", ["format"], unique=False)
    op.create_index("ix_assets_source_site", "assets", ["source_site"], unique=False)
    op.create_index("ix_assets_file_hash", "assets", ["file_hash"], unique=False)

    op.add_column(
        "quote_items",
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_quote_items_asset_id",
        "quote_items",
        "assets",
        ["asset_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_quote_items_asset_id", "quote_items", type_="foreignkey")
    op.drop_column("quote_items", "asset_id")
    op.drop_index("ix_assets_file_hash", table_name="assets")
    op.drop_index("ix_assets_source_site", table_name="assets")
    op.drop_index("ix_assets_format", table_name="assets")
    op.drop_table("assets")
