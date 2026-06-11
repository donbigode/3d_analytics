from datetime import date as _date, datetime
from decimal import Decimal
from pydantic import BaseModel


class DigestOut(BaseModel):
    date: _date
    provider: str
    body: str
    cached: bool
    created_at: datetime


class AutoNameOut(BaseModel):
    inbox_id: str
    name: str
    confidence: float | None = None
    why: str | None = None


class MarkupSuggestionOut(BaseModel):
    quote_id: str
    suggested_markup_pct: Decimal
    complexity: str | None = None
    rationale: str | None = None
    # Aggregate of Mercado Livre street prices used to ground the
    # recommendation. ``None`` when ML wasn't configured or every item
    # name was too generic to search.
    market_price_ref: Decimal | None = None


class VarianceOut(BaseModel):
    quote_id: str
    orcado: Decimal
    real: Decimal
    variance_pct: Decimal
    explanation: str


class PricingCitation(BaseModel):
    url: str
    title: str | None = None


class PricingOut(BaseModel):
    quote_id: str
    cost: Decimal
    suggested_price: Decimal
    floor: Decimal
    ceiling: Decimal
    # The estimated market total that anchored the suggestion (sum of
    # ML avg × quantity per item). ``None`` when no live market data
    # was available — see ``market_status`` to know why.
    market_price_ref: Decimal | None = None
    market_status: str = "estimado"  # "observado" when grounded in ML data
    rationale: str | None = None
    # URLs the LLM consulted via web_search to ground the recommendation.
    # Empty when the LLM didn't (or couldn't) search the web.
    sources: list[PricingCitation] = []


class VariantSuggestion(BaseModel):
    name: str
    material: str | None = None
    angle: str | None = None


class VariantsOut(BaseModel):
    item_id: str
    variants: list[VariantSuggestion]
