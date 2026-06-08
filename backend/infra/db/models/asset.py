"""Local-first library of 3D-printing files (.gcode, .3mf, .stl).

Assets are deduplicated by SHA-256 of the raw bytes — uploading the same
file twice (or downloading it from two different sources) returns the
existing row. The file lives at ``<STORAGE_DIR>/library/<format>/<hash>.<ext>``
so the disk path is content-addressed.

When the asset came from a remote source (Printables, Thingiverse, …)
``source_*`` columns store the attribution required by CC-BY-style licenses;
the same fields are surfaced verbatim on PDFs that reuse this asset.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.infra.db.base import Base


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)

    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    format: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)

    parsed_meta: Mapped[dict | None] = mapped_column(JSONB)

    # Attribution
    source_url: Mapped[str | None] = mapped_column(String(800))
    source_site: Mapped[str | None] = mapped_column(String(60), index=True)  # 'manual' | 'printables' | 'thingiverse' | 'makerworld'
    source_author: Mapped[str | None] = mapped_column(String(200))
    source_license: Mapped[str | None] = mapped_column(String(80))
    thumbnail_url: Mapped[str | None] = mapped_column(String(800))

    tags: Mapped[list[str] | None] = mapped_column(ARRAY(String(40)))
    notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
