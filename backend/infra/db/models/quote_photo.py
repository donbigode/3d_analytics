from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.infra.db.base import Base


class QuotePhoto(Base):
    """Foto anexada a um orçamento (capa) ou a um item (quote_item_id != NULL)."""
    __tablename__ = "quote_photos"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    quote_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("quotes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quote_item_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("quote_items.id", ondelete="CASCADE"), nullable=True, index=True
    )
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(40), nullable=False, default="image/jpeg")
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    width: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    height: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
