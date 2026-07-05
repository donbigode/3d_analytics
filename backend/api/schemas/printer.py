from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class PrintJobIn(BaseModel):
    machine: str
    job_uid: str
    filename: str | None = None
    status: str  # completed | cancelled | error
    filament_used_mm: Decimal = Decimal("0")
    print_duration_s: Decimal = Decimal("0")
    started_at: datetime | None = None
    finished_at: datetime | None = None
    raw: dict = Field(default_factory=dict)


class PrintJobLinkIn(BaseModel):
    quote_id: str
    spool_id: str
