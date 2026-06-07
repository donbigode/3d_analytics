from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class KeywordIdeaCreate(BaseModel):
    term: str = Field(..., min_length=1, max_length=120)
    notes: str | None = None


class KeywordIdeaOut(BaseModel):
    id: str
    term: str
    notes: str | None
    created_at: datetime


class ObservationOut(BaseModel):
    id: str
    keyword_id: str
    source: str
    metric: str
    value: Decimal
    raw_payload: Any | None
    taken_at: datetime


class SparkPoint(BaseModel):
    taken_at: datetime
    value: Decimal


class TopListing(BaseModel):
    title: str
    price: float | None = None
    sold: int = 0
    permalink: str | None = None


class RankingRow(BaseModel):
    id: str
    term: str
    score: Decimal
    interest: Decimal | None
    ml_volume: Decimal | None
    ml_avg_price: Decimal | None
    sparkline: list[SparkPoint]
    top_listings: list[TopListing] = []


class RefreshOut(BaseModel):
    observations_created: int
