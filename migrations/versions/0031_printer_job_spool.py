"""printer_jobs.spool_id (spool escolhido no atachar)

Revision ID: 0031_printer_job_spool
Revises: 0030_printer_jobs
Create Date: 2026-07-05 18:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = "0031_printer_job_spool"
down_revision: Union[str, Sequence[str], None] = "0030_printer_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("printer_jobs", sa.Column("spool_id", PG_UUID(as_uuid=True),
        sa.ForeignKey("spools.id", ondelete="SET NULL")))


def downgrade() -> None:
    op.drop_column("printer_jobs", "spool_id")
