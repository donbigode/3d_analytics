from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4
from sqlalchemy import String, Numeric, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from backend.infra.db.base import Base
from backend.core.models import SpoolStatus


class Spool(Base):
    __tablename__ = "spools"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    material_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    color: Mapped[str | None] = mapped_column(String(60))
    manufacturer: Mapped[str | None] = mapped_column(String(120))
    purchased_from: Mapped[str | None] = mapped_column(String(160))
    purchase_url: Mapped[str | None] = mapped_column(String(500))
    purchased_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    purchased_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    initial_grams: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    remaining_grams: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[SpoolStatus] = mapped_column(String(20), nullable=False, default=SpoolStatus.OPEN)
    notes: Mapped[str | None] = mapped_column(Text)
    # Qual produto (MaterialVersion) é esta bobina. Nullable: bobina cadastrada
    # antes do material, ou com a cor escrita diferente, não casa no backfill —
    # e inventar um vínculo errado é pior que deixar NULL.
    #
    # IDENTIDADE, NÃO PREÇO. O custo da bobina vem do seu próprio
    # purchased_price / initial_grams. Não derivar custo daqui via
    # price_per_kg_ref: seria trocar o preço pago por um preço de referência.
    material_version_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("material_versions.id")
    )
