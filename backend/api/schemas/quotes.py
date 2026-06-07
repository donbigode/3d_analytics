from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel

from backend.core.models import QuoteKind, QuoteStatus


class QuoteCreate(BaseModel):
    kind: QuoteKind
    client_id: str | None = None
    notes: str | None = None
    markup_pct: Decimal = Decimal("0")
    min_charge: Decimal = Decimal("0")


class QuoteUpdate(BaseModel):
    client_id: str | None = None
    notes: str | None = None
    markup_pct: Decimal | None = None
    min_charge: Decimal | None = None


class QuoteItemOut(BaseModel):
    id: str
    name: str
    filename: str
    gcode_meta: dict
    quantity: int
    subtotal: Decimal
    material_pending: bool = False
    pending_material_code: str | None = None


class QuoteItemUpdate(BaseModel):
    name: str | None = None
    quantity: int | None = None
    material_code: str | None = None


class QuoteServiceOut(BaseModel):
    id: str
    service_id: str
    quantity: Decimal
    rate: Decimal
    subtotal: Decimal


class QuoteOut(BaseModel):
    id: str
    kind: QuoteKind
    client_id: str | None
    status: QuoteStatus
    markup_pct: Decimal
    min_charge: Decimal
    notes: str | None
    items: list[QuoteItemOut]
    services: list[QuoteServiceOut]
    cost: Decimal
    total: Decimal
    pending_items: int = 0
    created_at: datetime
    finalized_at: datetime | None
    approved_at: datetime | None
    produced_at: datetime | None
    delivered_at: datetime | None


class ConsumptionAssignment(BaseModel):
    quote_item_id: str
    spool_id: str


class ProduceRequest(BaseModel):
    consumption: list[ConsumptionAssignment]


class ServiceLineCreate(BaseModel):
    service_id: str
    quantity: Decimal
    rate: Decimal | None = None  # if None, uses service.default_rate
