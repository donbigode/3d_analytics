"""Cached daily digests so opening the dashboard doesn't burn tokens.

The router asks for today's digest; if there's a row with `digest_date = today`
we serve from cache, otherwise generate, persist, return.
"""
from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import Date, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.infra.db.base import Base


class LLMDigest(Base):
    __tablename__ = "llm_digests"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    digest_date: Mapped[date] = mapped_column(Date, nullable=False, unique=True, index=True)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
