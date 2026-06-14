"""Production outcome events — one row per produce-cycle outcome.

Each time a quote leaves ``em_producao`` (Concluir/Falhar in Capacidade) we
record what happened: success or failure, how many attempts, a free-text
failure description, and a per-piece context snapshot (material/colour/
manufacturer + print characteristics). Failures also snapshot the wasted
grams. ``embedding`` and ``llm_tags`` stay NULL in Phase A — Phase B fills
them (vector store + LLM parsing) so Insights can suggest what to watch.
"""
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import String, Integer, Numeric, Text, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.infra.db.base import Base

EMBEDDING_DIM = 384


class ProductionEvent(Base):
    __tablename__ = "production_events"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    quote_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("quotes.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    failure_description: Mapped[str | None] = mapped_column(Text)
    context: Mapped[list | dict | None] = mapped_column(JSONB)
    grams_wasted: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    llm_tags: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
