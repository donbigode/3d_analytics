"""export_config (data lake export)

Revision ID: 0027_export_config
Revises: 0026_contabil_v2
Create Date: 2026-06-17 12:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0027_export_config"
down_revision: Union[str, Sequence[str], None] = "0026_contabil_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "export_config",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("destination", sa.String(20), nullable=False, server_default="s3"),
        sa.Column("s3_bucket", sa.String(200)),
        sa.Column("s3_region", sa.String(40)),
        sa.Column("s3_prefix", sa.String(300)),
        sa.Column("s3_access_key_id", sa.String(200)),
        sa.Column("s3_secret_access_key", sa.String(300)),
        sa.Column("databricks_host", sa.String(300)),
        sa.Column("databricks_token", sa.String(300)),
        sa.Column("databricks_volume_path", sa.String(400)),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column("last_run_status", sa.String(20)),
        sa.Column("last_run_detail", sa.Text),
    )


def downgrade() -> None:
    op.drop_table("export_config")
