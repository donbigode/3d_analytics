"""Suggest a sale price by triangulating cost, ML listings, Trends interest, history."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.llm_features.runner import call_json
from backend.core.models import QuoteKind, QuoteStatus
from backend.infra.db.models import (
    KeywordIdea,
    KeywordObservation,
    Quote,
    QuoteItem,
)


SYSTEM = (
    "Você sugere preço de venda em reais para uma peça impressa em 3D no Brasil, "
    "considerando custo de produção, faixa de preço de produtos parecidos no "
    "Mercado Livre, interesse no Google Trends e o markup histórico do dono. "
    "Responda APENAS em JSON: "
    "{\"suggested_price\": <number>, \"floor\": <number>, \"ceiling\": <number>, "
    "\"rationale\": \"<1-2 frases>\"}"
)


def _term_hint(items: list[QuoteItem]) -> str:
    """Best guess at a market search term using the item name."""
    if not items:
        return ""
    return items[0].name


async def suggest_price(
    session: AsyncSession,
    quote: Quote,
    *,
    orcado_cost: Decimal,
) -> dict:
    items = (
        await session.execute(select(QuoteItem).where(QuoteItem.quote_id == quote.id))
    ).scalars().all()

    # Best-effort: look for a KeywordIdea matching the item name to pull ML/Trends signals
    market_lines: list[str] = []
    if items:
        term_guess = items[0].name
        # find a keyword idea with similar term
        all_ideas = (await session.execute(select(KeywordIdea))).scalars().all()
        match = next(
            (k for k in all_ideas if term_guess.lower() in (k.term or "").lower()),
            None,
        )
        if match:
            obs = (
                await session.execute(
                    select(KeywordObservation).where(
                        KeywordObservation.keyword_id == match.id
                    )
                )
            ).scalars().all()
            for o in obs[-6:]:
                market_lines.append(f"  - {o.source}.{o.metric} = {float(o.value):.2f}")
    market_block = "\n".join(market_lines) if market_lines else "  (sem sinais de mercado coletados)"

    # Historical markup median
    history = (
        await session.execute(
            select(Quote.markup_pct).where(
                Quote.kind == QuoteKind.COMMERCIAL.value,
                Quote.status.in_(
                    [
                        QuoteStatus.APROVADO.value,
                        QuoteStatus.PRODUZIDO.value,
                        QuoteStatus.ENTREGUE.value,
                    ]
                ),
            )
        )
    ).scalars().all()
    markups = sorted(float(m) for m in history if m is not None)
    median_markup = markups[len(markups) // 2] if markups else 50.0

    user_prompt = (
        f"Custo de produção orçado: R${float(orcado_cost):.2f}\n"
        f"Markup mediano histórico: {median_markup:.0f}%\n"
        f"Item: {items[0].name if items else '?'}\n\n"
        f"Sinais de mercado (últimas observações):\n{market_block}\n\n"
        "Recomende preço de venda, com faixa razoável (floor/ceiling)."
    )
    return await call_json(session, system=SYSTEM, user=user_prompt, max_tokens=400)
