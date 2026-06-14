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
    retail_mode: bool | None = None


class QuoteItemOut(BaseModel):
    id: str
    name: str
    filename: str | None = None
    gcode_meta: dict
    quantity: int
    subtotal: Decimal
    # MaterialVersion UUID actually bound to this item — surfaced so the UI
    # can preselect it in the inline material dropdown. ``None`` when the
    # gcode was uploaded but no material was resolved.
    material_id: str | None = None
    is_multi_color: bool = False
    material_pending: bool = False
    pending_material_code: str | None = None
    model_source_url: str | None = None
    model_source_author: str | None = None
    model_source_license: str | None = None


class QuoteItemUpdate(BaseModel):
    name: str | None = None
    quantity: int | None = None
    # UUID of the chosen MaterialVersion (preferred). Used when the user
    # resolves a pending item or switches to a different product line.
    material_id: str | None = None
    # Legacy: polymer type string. Still accepted — auto-resolves when there's
    # exactly one current material of that type; rejects with 400 otherwise.
    material_code: str | None = None
    # Manual overrides for gcode metadata — used when the slicer dialect
    # wasn't recognised on upload or the user wants to correct the parse.
    time_s: float | None = None
    filament_m: float | None = None
    is_multi_color: bool | None = None
    model_source_url: str | None = None
    model_source_author: str | None = None
    model_source_license: str | None = None


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
    retail_mode: bool = False
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
    # Overrides informados na hora de produzir (quando o gcode não trouxe a
    # metragem). `grams` = total a debitar para a linha; tem precedência.
    # `filament_m` = metragem por unidade; calcula as gramas e é persistida
    # no item (para custo/analytics refletirem).
    grams: Decimal | None = None
    filament_m: float | None = None


class ProduceRequest(BaseModel):
    consumption: list[ConsumptionAssignment]


class CompleteRequest(BaseModel):
    attempts: int = 1


class FailRequest(BaseModel):
    failure_description: str
    attempts: int = 1


class ServiceLineCreate(BaseModel):
    service_id: str
    quantity: Decimal
    rate: Decimal | None = None  # if None, uses service.default_rate
