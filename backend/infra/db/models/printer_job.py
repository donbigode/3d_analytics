from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import String, Numeric, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.infra.db.base import Base
from backend.core.models import PrinterJobStatus


class PrinterJob(Base):
    __tablename__ = "printer_jobs"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    machine: Mapped[str] = mapped_column(String(120), nullable=False)
    job_uid: Mapped[str] = mapped_column(String(120), nullable=False)
    filename: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    filament_used_mm: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    time_s: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    grams: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    inbox_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=PrinterJobStatus.PENDING
    )
    quote_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("quotes.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
