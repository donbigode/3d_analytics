"""quote_items.model_source_url / author / license

Revision ID: 0012_model_source
Revises: 0011_youtube_key
Create Date: 2026-06-08 01:30:00.000000

Adds three optional columns so each printed item can cite the source model
(Printables, MakerWorld, Thingiverse, …) in the PDF — important for CC-BY
compliance and downstream auditing.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0012_model_source"
down_revision: Union[str, Sequence[str], None] = "0011_youtube_key"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("quote_items", sa.Column("model_source_url", sa.String(length=500), nullable=True))
    op.add_column("quote_items", sa.Column("model_source_author", sa.String(length=160), nullable=True))
    op.add_column("quote_items", sa.Column("model_source_license", sa.String(length=80), nullable=True))


def downgrade() -> None:
    op.drop_column("quote_items", "model_source_license")
    op.drop_column("quote_items", "model_source_author")
    op.drop_column("quote_items", "model_source_url")
