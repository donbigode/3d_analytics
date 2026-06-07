from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


InsightScopeKind = Literal["material_failure", "material_price"]
InsightStatus = Literal["open", "applied", "dismissed"]


class InsightOut(BaseModel):
    id: str
    scope_kind: InsightScopeKind
    scope_ref: str
    observed_value: Decimal
    current_value: Decimal
    suggested_value: Decimal
    delta_pct: Decimal
    sample_size: int
    status: InsightStatus
    computed_at: datetime


class InsightApplyOut(BaseModel):
    id: str
    status: InsightStatus
    material_code: str
    field: str
    previous_value: Decimal
    new_value: Decimal
