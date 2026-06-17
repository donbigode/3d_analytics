from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, false
from sqlalchemy.orm import Mapped, mapped_column

from backend.infra.db.base import Base


class ExportConfig(Base):
    """Config singleton (id=1) do export pro data lake (S3 ou Databricks)."""
    __tablename__ = "export_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    destination: Mapped[str] = mapped_column(String(20), nullable=False, default="s3", server_default="s3")
    s3_bucket: Mapped[str | None] = mapped_column(String(200))
    s3_region: Mapped[str | None] = mapped_column(String(40))
    s3_prefix: Mapped[str | None] = mapped_column(String(300))
    s3_access_key_id: Mapped[str | None] = mapped_column(String(200))
    s3_secret_access_key: Mapped[str | None] = mapped_column(String(300))
    databricks_host: Mapped[str | None] = mapped_column(String(300))
    databricks_token: Mapped[str | None] = mapped_column(String(300))
    databricks_volume_path: Mapped[str | None] = mapped_column(String(400))
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_run_status: Mapped[str | None] = mapped_column(String(20))
    last_run_detail: Mapped[str | None] = mapped_column(Text)
