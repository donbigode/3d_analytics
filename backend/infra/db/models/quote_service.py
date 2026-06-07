from decimal import Decimal
from uuid import UUID, uuid4
from sqlalchemy import Numeric, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from backend.infra.db.base import Base


class QuoteService(Base):
    __tablename__ = "quote_services"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    quote_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("quotes.id", ondelete="CASCADE"), nullable=False)
    service_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("services.id"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
