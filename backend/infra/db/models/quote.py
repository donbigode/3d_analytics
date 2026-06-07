from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4
from sqlalchemy import String, Numeric, DateTime, Text, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from backend.infra.db.base import Base
from backend.core.models import QuoteKind, QuoteStatus


class Quote(Base):
    __tablename__ = "quotes"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    kind: Mapped[QuoteKind] = mapped_column(String(20), nullable=False)
    client_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("clients.id"))
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    status: Mapped[QuoteStatus] = mapped_column(String(20), nullable=False, default=QuoteStatus.DRAFT)
    markup_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    min_charge: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    produced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
