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
    temporal_window: str = "week"
    source_provider: str | None = None
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


class TopRedditPost(BaseModel):
    title: str
    subreddit: str = ""
    score: int = 0
    comments: int = 0
    permalink: str | None = None


class RankingRow(BaseModel):
    id: str
    term: str
    score: Decimal
    interest: Decimal | None
    wiki_views: Decimal | None = None
    ml_volume: Decimal | None
    ml_avg_price: Decimal | None
    reddit_score: Decimal | None = None
    reddit_comments: Decimal | None = None
    sparkline: list[SparkPoint]
    top_listings: list[TopListing] = []
    top_reddit_posts: list[TopRedditPost] = []
    temporal_window: str = "week"
    source_provider: str | None = None  # 'anthropic' | 'gemini' | 'openai' | None (manual)


class RefreshOut(BaseModel):
    observations_created: int


# ---------------- LLM suggestions ----------------

class SuggestionOut(BaseModel):
    id: str
    term: str
    rationale: str | None
    provider: str
    recurrence_score: Decimal
    status: str
    promoted_keyword_id: str | None
    suggested_at: datetime


class SuggestionPromoteOut(BaseModel):
    suggestion_id: str
    keyword_id: str
    term: str


class LLMRefreshOut(BaseModel):
    source: str
    status: str
    items_created: int
    error: str | None
    metadata: dict | None


# ---------------- Source metrics ----------------

class SourceMetric(BaseModel):
    source: str
    enabled: bool
    last_run_at: datetime | None
    last_status: str | None
    last_error: str | None
    runs_24h: int
    items_created_24h: int
    errors_7d: int
    avg_duration_ms_7d: int | None


class SourceMetricsOut(BaseModel):
    sources: list[SourceMetric]
