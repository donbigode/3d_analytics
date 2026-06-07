from decimal import Decimal
from uuid import UUID, uuid4
from sqlalchemy import String, Numeric, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from backend.infra.db.base import Base


class QuoteItem(Base):
    __tablename__ = "quote_items"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    quote_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("quotes.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    gcode_meta: Mapped[dict] = mapped_column(JSONB, nullable=False)
    material_version_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("material_versions.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(nullable=False, default=1)
    depreciation_rate_override: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    failure_rate_override: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
