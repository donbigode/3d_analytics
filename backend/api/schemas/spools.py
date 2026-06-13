from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel
from backend.core.models import SpoolStatus


class SpoolCreate(BaseModel):
    material_type: str
    color: str | None = None
    manufacturer: str | None = None
    purchased_from: str | None = None  # onde foi comprado (loja/marketplace)
    purchase_url: str | None = None    # link da compra
    purchased_at: datetime
    purchased_price: Decimal
    initial_grams: Decimal
    remaining_grams: Decimal
    status: SpoolStatus = SpoolStatus.OPEN
    notes: str | None = None


class SpoolUpdate(BaseModel):
    material_type: str | None = None
    color: str | None = None
    manufacturer: str | None = None
    purchased_from: str | None = None
    purchase_url: str | None = None
    purchased_at: datetime | None = None
    purchased_price: Decimal | None = None
    initial_grams: Decimal | None = None
    remaining_grams: Decimal | None = None
    status: SpoolStatus | None = None
    notes: str | None = None


class SpoolOut(BaseModel):
    id: str
    material_type: str
    color: str | None
    manufacturer: str | None
    purchased_from: str | None
    purchase_url: str | None
    purchased_at: datetime
    purchased_price: Decimal
    initial_grams: Decimal
    remaining_grams: Decimal
    status: SpoolStatus
    notes: str | None
