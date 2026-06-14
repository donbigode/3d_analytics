"""Sugestões de produção (Fase B): embeddings das falhas + uma chamada LLM
sob demanda que resume 'o que vigiar' por material. Resultado cacheado."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.llm_features.runner import call_json
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


_SYSTEM = (
    "Você é um especialista em impressão 3D FDM. Recebe uma lista de falhas de "
    "produção agrupadas por material e responde, em português, o que vigiar para "
    "evitar cada tipo de falha. Responda APENAS JSON no formato "
    '{"suggestions": [{"material_type": str, "advice": str}]}. '
    "advice deve ser curto (1-2 frases), prático e específico ao material."
)


async def gather_failures(session: AsyncSession) -> list[dict]:
    """Falhas com texto, deduplicando descrições muito similares (cosine>=0.92)
    quando há embedding, para o prompt ficar compacto."""
    rows = (
        await session.execute(
            select(ProductionEvent)
            .where(ProductionEvent.outcome == ProductionOutcome.FAILURE)
            .order_by(ProductionEvent.created_at.desc())
        )
    ).scalars().all()
    out: list[dict] = []
    seen_vecs: list[list[float]] = []
    for e in rows:
        text = failure_event_text(e)
        if not text:
            continue
        if e.embedding is not None:
            vec = list(e.embedding)
            if any(cosine_similarity(vec, s) >= 0.92 for s in seen_vecs):
                continue
            seen_vecs.append(vec)
        mats = sorted(
            {
                (p or {}).get("material_type")
                for p in (e.context or [])
                if (p or {}).get("material_type")
            }
        )
        out.append({"materials": mats or ["—"], "text": text, "attempts": e.attempts})
    return out


async def generate_suggestions(session: AsyncSession) -> dict:
    """Embeda pendências, monta prompt e chama o LLM 1x; persiste no cache."""
    await fill_failure_embeddings(session)
    failures = await gather_failures(session)
    if not failures:
        return {"suggestions": [], "source_count": 0, "provider": None}

    lines = [
        f"- [{', '.join(f['materials'])}] (tentativas={f['attempts']}): {f['text']}"
        for f in failures
    ]
    user = "Falhas registradas:\n" + "\n".join(lines)

    parsed = await call_json(session, system=_SYSTEM, user=user, max_tokens=900)
    suggestions = parsed.get("suggestions") or []
    session.add(
        ProductionSuggestion(
            body={"suggestions": suggestions},
            provider="llm",
            source_count=len(failures),
        )
    )
    await session.commit()
    return {
        "suggestions": suggestions,
        "source_count": len(failures),
        "provider": "llm",
    }
