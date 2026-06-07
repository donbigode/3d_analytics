from decimal import Decimal
from uuid import UUID, uuid4
from sqlalchemy import String, Numeric, Boolean
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from backend.infra.db.base import Base
from backend.core.models import ServiceKind, ServiceUnit


class Service(Base):
    __tablename__ = "services"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    unit: Mapped[ServiceUnit] = mapped_column(String(10), nullable=False)
    default_rate: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    kind: Mapped[ServiceKind] = mapped_column(String(10), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
