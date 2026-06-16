from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Numeric, String, Text, false, func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.infra.db.base import Base


class Sale(Base):
    """Linha contábil materializada a partir de um orçamento comercial.

    Campos-espelho (quote_status/quote_total/cpv_calc/client_id) são
    reescritos a cada sync. Campos editáveis (is_sold, confirmed_revenue,
    variable_costs, cpv_override, sold_at, notes) são preservados.
    """
    __tablename__ = "sales"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    quote_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("quotes.id", ondelete="CASCADE"),
        nullable=False, unique=True,
    )
    # Espelho — reescrito no sync
    quote_status: Mapped[str] = mapped_column(String(20), nullable=False)
    quote_total: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    cpv_calc: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    client_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("clients.id", ondelete="SET NULL")
    )
    is_stale: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    # Editável — preservado no sync
    is_sold: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    confirmed_revenue: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    variable_costs: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=0, server_default="0"
    )
    cpv_override: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    sold_at: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
