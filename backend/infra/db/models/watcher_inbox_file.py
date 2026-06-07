from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import String, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from backend.infra.db.base import Base
from backend.core.models import WatcherInboxStatus


class WatcherInboxFile(Base):
    __tablename__ = "watcher_inbox_files"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    file_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    original_path: Mapped[str] = mapped_column(String(500), nullable=False)
    parsed_meta: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[WatcherInboxStatus] = mapped_column(String(20), nullable=False, default=WatcherInboxStatus.PENDING)
    quote_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("quotes.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
