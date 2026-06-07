from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4
from sqlalchemy import String, Numeric, DateTime, Boolean, Index, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from backend.infra.db.base import Base


class MaterialVersion(Base):
    __tablename__ = "material_versions"
    __table_args__ = (
        Index("ix_material_current", "material_code", "is_current"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    material_code: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    density_g_cm3: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    price_per_kg_ref: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    failure_rate_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
