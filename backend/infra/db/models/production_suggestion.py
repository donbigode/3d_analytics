"""Cache da última geração de sugestões de produção (padrão LLMDigest:
gera sob demanda, persiste, relê sem gastar token). `source_count` guarda
quantos eventos existiam na geração, para sinalizar 'desatualizado'."""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Integer, String, DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.infra.db.base import Base


class ProductionSuggestion(Base):
    __tablename__ = "production_suggestions"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    body: Mapped[list | dict] = mapped_column(JSONB, nullable=False)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
