from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4
from sqlalchemy import String, Numeric, DateTime, Boolean, Index, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from backend.infra.db.base import Base


class MaterialVersion(Base):
    """SCD2 row for a (material_type, manufacturer, color) product line.

    ``material_type`` is the polymer family that matches what the gcode
    declares (PLA, PETG, ABS, ASA, PLA-CF, TPU…). ``manufacturer`` and
    ``color`` distinguish concrete products from each other.
    """

    __tablename__ = "material_versions"
    __table_args__ = (
        Index("ix_material_current", "material_type", "is_current"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    material_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    manufacturer: Mapped[str | None] = mapped_column(String(120))
    color: Mapped[str | None] = mapped_column(String(80))
    density_g_cm3: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    price_per_kg_ref: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    failure_rate_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    # Refugo (waste) — fraction of declared filament that turns into purges,
    # brims, supports and color-change towers. Applied to ``grams`` before
    # the failure multiplier. The single-color value covers brim/skirt/first
    # layer purge (typically 1–4%); the multi-color one absorbs the purge
    # tower for color/material swaps (typically 15–35%).
    single_color_waste_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("2")
    )
    multi_color_waste_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("20")
    )
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
