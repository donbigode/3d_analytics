"""Daily digest — narrative summary of the dashboard + radar state."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.llm_features.runner import call_text
from backend.core.models import QuoteKind, QuoteStatus, WatcherInboxStatus
from backend.infra.db.models import (
    LLMSuggestion,
    Quote,
    Settings,
    Spool,
    WatcherInboxFile,
)


SYSTEM = (
    "Você é um analista pessoal de um casal que toca um serviço de impressão 3D no "
    "Brasil. Escreva briefings curtos (3 a 5 frases), objetivos, em português, "
    "destacando o que mudou, o que precisa de atenção, e UMA sugestão acionável. "
    "Sem markdown, sem listas, sem títulos — só prosa direta."
)


async def _build_context(session: AsyncSession) -> str:
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    prev_week = now - timedelta(days=14)

    settings_row = await session.get(Settings, 1)

    # Receita das duas últimas semanas (commercial >= aprovado)
    quotes_recent = (
        await session.execute(
            select(Quote).where(Quote.created_at >= prev_week)
        )
    ).scalars().all()

    rev_this, rev_prev = Decimal(0), Decimal(0)
    produced_this, produced_prev = 0, 0
    new_drafts_today = 0
    today = now.date()

    for q in quotes_recent:
        in_this_week = q.created_at and q.created_at >= week_ago
        in_prev_week = q.created_at and prev_week <= q.created_at < week_ago
        if q.kind == QuoteKind.COMMERCIAL.value:
            if q.status in (QuoteStatus.APROVADO.value, QuoteStatus.PRODUZIDO.value, QuoteStatus.ENTREGUE.value):
                # rough revenue proxy: sum of min_charge + markup over nothing; we'd
                # need to recompute total. For digest purposes, count + rough mean.
                if in_this_week:
                    rev_this += (q.min_charge or Decimal(0)) + (q.markup_pct or Decimal(0))
                if in_prev_week:
                    rev_prev += (q.min_charge or Decimal(0)) + (q.markup_pct or Decimal(0))
            if q.status in (QuoteStatus.PRODUZIDO.value, QuoteStatus.ENTREGUE.value):
                if in_this_week:
                    produced_this += 1
                if in_prev_week:
                    produced_prev += 1
        if q.created_at and q.created_at.date() == today and q.status == QuoteStatus.DRAFT.value:
            new_drafts_today += 1

    low_threshold = settings_row.low_spool_threshold_g if settings_row else Decimal(100)
    low_spools = (
        await session.execute(
            select(Spool).where(Spool.remaining_grams < low_threshold)
        )
    ).scalars().all()

    pending_inbox = (
        await session.execute(
            select(WatcherInboxFile).where(
                WatcherInboxFile.status == WatcherInboxStatus.PENDING.value
            )
        )
    ).scalars().all()

    pending_suggestions = (
        await session.execute(
            select(LLMSuggestion).where(LLMSuggestion.status == "pending")
        )
    ).scalars().all()

    lines: list[str] = []
    lines.append(f"Data: {today.isoformat()}.")
    lines.append(
        f"Esta semana: {produced_this} impressões produzidas ({produced_prev} na semana anterior)."
    )
    lines.append(f"Drafts criados hoje: {new_drafts_today}.")
    if low_spools:
        names = ", ".join(f"{s.material_code} {int(s.remaining_grams)}g" for s in low_spools[:5])
        lines.append(f"Spools abaixo do limiar ({int(low_threshold)}g): {names}.")
    if pending_inbox:
        names = ", ".join(
            (it.original_path.split("/")[-1] or "?") for it in pending_inbox[:5]
        )
        lines.append(f"Inbox aguardando atribuição ({len(pending_inbox)}): {names}.")
    if pending_suggestions:
        terms = ", ".join((s.term for s in pending_suggestions[:5]))
        lines.append(
            f"Sugestões de tendência ({len(pending_suggestions)}) no inbox: {terms}."
        )
    return "\n".join(lines)


async def generate_digest(session: AsyncSession) -> tuple[str, str]:
    """Return ``(body, provider_used)`` for the daily digest."""
    context = await _build_context(session)
    user_prompt = (
        "A seguir, fatos numéricos da operação hoje:\n\n"
        f"{context}\n\n"
        "Escreva o briefing diário em 3-5 frases."
    )
    body = await call_text(session, system=SYSTEM, user=user_prompt, max_tokens=400)
    # Discover which provider answered — heuristic: re-read settings.preferred
    settings_row = await session.get(Settings, 1)
    provider = settings_row.preferred_llm_provider if settings_row else "anthropic"
    return body, provider
