from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4
from sqlalchemy import Numeric, ForeignKey, DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from backend.infra.db.base import Base


class MaterialConsumption(Base):
    __tablename__ = "material_consumptions"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    quote_item_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("quote_items.id", ondelete="CASCADE"), nullable=False)
    # Qual linha de filamento originou este consumo. NULL = consumo anterior à
    # 0034. Sem isto, várias linhas de consumo no mesmo item são ambíguas entre
    # "duas cores" e "duas tentativas" (reimpressão) — e a segunda já existia.
    # Não dá para inferir por spool_id (duas cores podem sair do mesmo produto)
    # nem por consumed_at (heurística sobre dinheiro).
    quote_item_filament_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("quote_item_filaments.id", ondelete="SET NULL")
    )
    spool_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("spools.id"), nullable=False)
    grams_used: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    consumed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    unit_cost_snapshot: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
