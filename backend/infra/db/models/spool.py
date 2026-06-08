from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4
from sqlalchemy import String, Numeric, DateTime, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from backend.infra.db.base import Base
from backend.core.models import SpoolStatus


class Spool(Base):
    __tablename__ = "spools"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    material_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    purchased_from: Mapped[str | None] = mapped_column(String(160))
    purchase_url: Mapped[str | None] = mapped_column(String(500))
    purchased_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    purchased_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    initial_grams: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    remaining_grams: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[SpoolStatus] = mapped_column(String(20), nullable=False, default=SpoolStatus.OPEN)
    notes: Mapped[str | None] = mapped_column(Text)
