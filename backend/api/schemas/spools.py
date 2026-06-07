from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel
from backend.core.models import SpoolStatus


class SpoolCreate(BaseModel):
    material_code: str
    supplier: str | None = None
    batch_code: str | None = None
    purchased_at: datetime
    purchased_price: Decimal
    initial_grams: Decimal
    remaining_grams: Decimal
    status: SpoolStatus = SpoolStatus.OPEN
    notes: str | None = None


class SpoolUpdate(BaseModel):
    material_code: str | None = None
    supplier: str | None = None
    batch_code: str | None = None
    purchased_at: datetime | None = None
    purchased_price: Decimal | None = None
    initial_grams: Decimal | None = None
    remaining_grams: Decimal | None = None
    status: SpoolStatus | None = None
    notes: str | None = None


class SpoolOut(BaseModel):
    id: str
    material_code: str
    supplier: str | None
    batch_code: str | None
    purchased_at: datetime
    purchased_price: Decimal
    initial_grams: Decimal
    remaining_grams: Decimal
    status: SpoolStatus
    notes: str | None
