from decimal import Decimal
from datetime import datetime
from pydantic import BaseModel


class MaterialCreate(BaseModel):
    material_code: str
    name: str
    density_g_cm3: Decimal
    price_per_kg_ref: Decimal
    failure_rate_pct: Decimal = Decimal("0")


class MaterialUpdate(BaseModel):
    name: str | None = None
    density_g_cm3: Decimal | None = None
    price_per_kg_ref: Decimal | None = None
    failure_rate_pct: Decimal | None = None


class MaterialOut(BaseModel):
    id: str
    material_code: str
    name: str
    density_g_cm3: Decimal
    price_per_kg_ref: Decimal
    failure_rate_pct: Decimal
    is_current: bool
    effective_from: datetime
    effective_to: datetime | None
