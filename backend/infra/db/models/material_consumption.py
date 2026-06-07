from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4
from sqlalchemy import Numeric, ForeignKey, DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from backend.infra.db.base import Base


class MaterialConsumption(Base):
    __tablename__ = "material_consumptions"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    quote_item_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("quote_items.id", ondelete="CASCADE"), nullable=False)
    spool_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("spools.id"), nullable=False)
    grams_used: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    consumed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    unit_cost_snapshot: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
