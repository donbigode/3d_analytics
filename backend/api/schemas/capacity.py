from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel


class ForecastJobOut(BaseModel):
    quote_id: str
    name: str
    hours: Decimal
    eta: datetime


class ForecastOut(BaseModel):
    hours_per_day: Decimal
    queue_hours: Decimal
    queue_jobs: int
    days_until_clear: int
    next_available_at: datetime
    jobs: list[ForecastJobOut]


class InProductionJob(BaseModel):
    quote_id: str
    name: str
    kind: str
    hours: Decimal
    entered_at: datetime | None


class InProductionOut(BaseModel):
    jobs: list[InProductionJob]


class QuoteEtaOut(BaseModel):
    quote_id: str
    in_queue: bool
    position: int | None
    hours: Decimal
    eta: datetime | None
    next_available_at: datetime
