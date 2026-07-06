"""printer_jobs (ingestão de jobs da impressora)

Revision ID: 0030_printer_jobs
Revises: 0029_people_quote_people
Create Date: 2026-07-05 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB

revision: str = "0030_printer_jobs"
down_revision: Union[str, Sequence[str], None] = "0029_people_quote_people"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "printer_jobs",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("machine", sa.String(120), nullable=False),
        sa.Column("job_uid", sa.String(120), nullable=False),
        sa.Column("filename", sa.String(500)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("filament_used_mm", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("time_s", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("grams", sa.Numeric(10, 2)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("raw", JSONB, nullable=False, server_default="{}"),
        sa.Column("inbox_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("quote_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("quotes.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_unique_constraint(
        "uq_printer_jobs_machine_job", "printer_jobs", ["machine", "job_uid"]
    )


def downgrade() -> None:
    op.drop_table("printer_jobs")
