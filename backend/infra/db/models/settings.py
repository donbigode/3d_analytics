from decimal import Decimal
from sqlalchemy import String, Numeric, Integer
from sqlalchemy.orm import Mapped, mapped_column
from backend.infra.db.base import Base


class Settings(Base):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    energy_kwh_price: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, default=Decimal("0.95"))
    printer_power_w: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False, default=Decimal("150"))
    printer_depreciation_per_hour: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BRL")
    business_name: Mapped[str] = mapped_column(String(120), nullable=False, default="Sua Marca")
    business_tagline: Mapped[str | None] = mapped_column(String(200))
    logo_path: Mapped[str | None] = mapped_column(String(255))
    brand_color_primary: Mapped[str] = mapped_column(String(9), nullable=False, default="#111827")
    stalled_quote_alert_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    low_spool_threshold_g: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("100"))
    printer_hours_per_day: Mapped[int] = mapped_column(Integer, nullable=False, default=22)
