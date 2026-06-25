"""people + quote_people (atribuição de projeto pessoal)

Revision ID: 0029_people_quote_people
Revises: 0028_quote_photos
Create Date: 2026-06-25 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = "0029_people_quote_people"
down_revision: Union[str, Sequence[str], None] = "0028_quote_photos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "people",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_unique_constraint("uq_people_name", "people", ["name"])
    op.create_table(
        "quote_people",
        sa.Column("quote_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("quotes.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("person_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("people.id", ondelete="CASCADE"), primary_key=True),
    )


def downgrade() -> None:
    op.drop_table("quote_people")
    op.drop_table("people")
