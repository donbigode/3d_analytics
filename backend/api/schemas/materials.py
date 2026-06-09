from decimal import Decimal
from datetime import datetime
from pydantic import BaseModel


class MaterialCreate(BaseModel):
    material_type: str          # PLA, PETG, ABS, ASA, PLA-CF, TPU, …
    name: str
    manufacturer: str | None = None
    color: str | None = None
    density_g_cm3: Decimal
    price_per_kg_ref: Decimal
    failure_rate_pct: Decimal = Decimal("0")
    single_color_waste_pct: Decimal = Decimal("2")
    multi_color_waste_pct: Decimal = Decimal("20")


class MaterialUpdate(BaseModel):
    name: str | None = None
    manufacturer: str | None = None
    color: str | None = None
    density_g_cm3: Decimal | None = None
    price_per_kg_ref: Decimal | None = None
    failure_rate_pct: Decimal | None = None
    single_color_waste_pct: Decimal | None = None
    multi_color_waste_pct: Decimal | None = None


class MaterialOut(BaseModel):
    id: str
    material_type: str
    name: str
    manufacturer: str | None
    color: str | None
    density_g_cm3: Decimal
    price_per_kg_ref: Decimal
    failure_rate_pct: Decimal
    single_color_waste_pct: Decimal
    multi_color_waste_pct: Decimal
    is_current: bool
    effective_from: datetime
    effective_to: datetime | None
