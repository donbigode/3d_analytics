"""Sugestões de produção (Fase B): embeddings das falhas + uma chamada LLM
sob demanda que resume 'o que vigiar' por material. Resultado cacheado."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.llm_features.runner import LLMUnavailable, call_json
from backend.core.models import ProductionOutcome
from backend.core.trends.embeddings import cosine_similarity, embed
from backend.infra.db.models import ProductionEvent, ProductionSuggestion


def failure_event_text(ev: Any) -> str:
    """Texto compacto da falha para embedding e prompt."""
    parts: list[str] = []
    for piece in (ev.context or []):
        p = piece or {}
        mat = " ".join(
            str(x)
            for x in [p.get("material_type"), p.get("color"), p.get("manufacturer")]
            if x
        )
        chars: list[str] = []
        if p.get("is_multi_color"):
            chars.append("multicor")
        if p.get("filament_m"):
            chars.append(f"{p['filament_m']}m")
        if p.get("time_s"):
            chars.append(f"{round(float(p['time_s']) / 3600, 1)}h")
        seg = mat
        if chars:
            seg += " (" + ", ".join(chars) + ")"
        if seg.strip():
            parts.append(seg.strip())
    ctx = "; ".join(parts)
    desc = (ev.failure_description or "").strip()
    return f"{ctx}: {desc}" if ctx else desc


async def fill_failure_embeddings(session: AsyncSession) -> int:
    """Embeda falhas que ainda não têm vetor. Retorna quantas preencheu."""
    rows = (
        await session.execute(
            select(ProductionEvent).where(
                ProductionEvent.outcome == ProductionOutcome.FAILURE,
                ProductionEvent.embedding.is_(None),
            )
        )
    ).scalars().all()
    pending = [(e, failure_event_text(e)) for e in rows]
    pending = [(e, t) for e, t in pending if t]
    if not pending:
        return 0
    vectors = await embed([t for _, t in pending])
    for (e, _), vec in zip(pending, vectors):
        e.embedding = vec
    await session.commit()
    return len(pending)
