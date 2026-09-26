from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.infra.db.base import Base


class QuoteItemFilament(Base):
    """Um filamento usado por um item — cor, material e gramas.

    Autoritativa para custo. ``quote_items.material_version_id`` é o derivado
    desta tabela: sempre igual ao material da linha de ``position = 1``.

    ``grams_unit`` é **por peça**, e é NULL de propósito para todo item que
    existia antes da migração 0034: NULL significa "derive do ``gcode_meta``
    como sempre". Congelar o valor calculado no backfill faria o histórico
    parar de reprecificar quando a densidade do material fosse ajustada.

    Item com mais de uma linha exige ``grams_unit`` em **todas** — não se
    deriva do gcode o que é ambíguo entre N cores.
    """

    __tablename__ = "quote_item_filaments"
    __table_args__ = (
        UniqueConstraint("quote_item_id", "position", name="uq_quote_item_filament_pos"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    quote_item_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("quote_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    material_version_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("material_versions.id"), nullable=False
    )
    grams_unit: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    position: Mapped[int] = mapped_column(nullable=False)
