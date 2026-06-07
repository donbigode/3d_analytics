from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.infra.db.base import Base


class CalibrationInsight(Base):
    """A surfaced suggestion comparing real consumption vs declared/catalog.

    scope_kind: "material_failure" | "material_price"
    scope_ref:  the material_code for those kinds.
    status:     "open" | "applied" | "dismissed"
    """

    __tablename__ = "calibration_insights"
    __table_args__ = (
        Index("ix_calibration_insights_status", "status"),
        Index("ix_calibration_insights_scope", "scope_kind", "scope_ref"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    scope_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    scope_ref: Mapped[str] = mapped_column(String(80), nullable=False)
    observed_value: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    current_value: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    suggested_value: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    delta_pct: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
