from decimal import Decimal
from pydantic import BaseModel
from backend.core.models import ServiceKind, ServiceUnit


class ServiceCreate(BaseModel):
    name: str
    unit: ServiceUnit
    default_rate: Decimal
    kind: ServiceKind
    is_active: bool = True


class ServiceUpdate(BaseModel):
    name: str | None = None
    unit: ServiceUnit | None = None
    default_rate: Decimal | None = None
    kind: ServiceKind | None = None
    is_active: bool | None = None


class ServiceOut(BaseModel):
    id: str
    name: str
    unit: ServiceUnit
    default_rate: Decimal
    kind: ServiceKind
    is_active: bool
