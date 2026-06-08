"""material_versions: rename material_code→material_type + add manufacturer/color
spools: drop batch_code, rename supplier→purchased_from, add purchase_url

Revision ID: 0014_mat_type_color
Revises: 0013_llm_digests
Create Date: 2026-06-08 18:00:00.000000

Semantic refactor:
- A "material" is now uniquely a (material_type, manufacturer, color) trio.
  ``material_type`` keeps matching what the gcode header declares (PLA, PETG, …)
  while manufacturer + color let the user track different physical products of
  the same family.
- Spool drops ``batch_code`` (unused) and renames ``supplier`` to
  ``purchased_from`` (more intuitive). Adds ``purchase_url`` for the order
  receipt link.

Existing rows preserve their data — only column names move.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0014_mat_type_color"
down_revision: Union[str, Sequence[str], None] = "0013_llm_digests"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- material_versions ---
    # Old indexes referencing material_code.
    op.drop_index("ix_material_current", table_name="material_versions")
    op.drop_index("ix_material_versions_material_code", table_name="material_versions")

    op.alter_column("material_versions", "material_code", new_column_name="material_type")
    op.add_column(
        "material_versions",
        sa.Column("manufacturer", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "material_versions",
        sa.Column("color", sa.String(length=80), nullable=True),
    )

    op.create_index(
        "ix_material_versions_material_type",
        "material_versions",
        ["material_type"],
        unique=False,
    )
    op.create_index(
        "ix_material_current",
        "material_versions",
        ["material_type", "is_current"],
        unique=False,
    )

    # --- spools ---
    op.drop_index("ix_spools_material_code", table_name="spools")
    op.alter_column("spools", "material_code", new_column_name="material_type")
    op.create_index(
        "ix_spools_material_type", "spools", ["material_type"], unique=False
    )
    op.drop_column("spools", "batch_code")
    op.alter_column("spools", "supplier", new_column_name="purchased_from")
    # widen purchased_from from 120 → 160 to accommodate longer marketplace names
    op.alter_column(
        "spools",
        "purchased_from",
        existing_type=sa.String(length=120),
        type_=sa.String(length=160),
        existing_nullable=True,
    )
    op.add_column(
        "spools",
        sa.Column("purchase_url", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("spools", "purchase_url")
    op.alter_column(
        "spools",
        "purchased_from",
        existing_type=sa.String(length=160),
        type_=sa.String(length=120),
        existing_nullable=True,
    )
    op.alter_column("spools", "purchased_from", new_column_name="supplier")
    op.add_column("spools", sa.Column("batch_code", sa.String(length=120), nullable=True))
    op.drop_index("ix_spools_material_type", table_name="spools")
    op.alter_column("spools", "material_type", new_column_name="material_code")
    op.create_index("ix_spools_material_code", "spools", ["material_code"])

    op.drop_index("ix_material_current", table_name="material_versions")
    op.drop_index("ix_material_versions_material_type", table_name="material_versions")
    op.drop_column("material_versions", "color")
    op.drop_column("material_versions", "manufacturer")
    op.alter_column("material_versions", "material_type", new_column_name="material_code")
    op.create_index(
        "ix_material_versions_material_code",
        "material_versions",
        ["material_code"],
        unique=False,
    )
    op.create_index(
        "ix_material_current",
        "material_versions",
        ["material_code", "is_current"],
        unique=False,
    )
