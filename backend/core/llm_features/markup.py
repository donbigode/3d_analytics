"""Suggest a markup percentage based on quote complexity + historical patterns."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.llm_features.runner import call_json
from backend.core.models import QuoteKind, QuoteStatus
from backend.infra.db.models import Quote, QuoteItem


SYSTEM = (
    "Você é um analista que sugere percentuais de markup para orçamentos de "
    "impressão 3D no Brasil, considerando complexidade do gcode (tempo, peso, "
    "número de peças, multi-color) e o histórico do dono. Devolve recomendação "
    "concreta. Responda APENAS em JSON: "
    "{\"suggested_markup_pct\": <number>, \"rationale\": \"<1-2 frases>\", "
    "\"complexity\": \"baixa|média|alta\"}"
)


async def suggest_markup(session: AsyncSession, quote: Quote) -> dict:
    items = (
        await session.execute(select(QuoteItem).where(QuoteItem.quote_id == quote.id))
    ).scalars().all()

    total_time = sum(int(it.gcode_meta.get("time_s") or 0) for it in items)
    total_filament = sum(float(it.gcode_meta.get("filament_m") or 0) for it in items)
    materials = sorted({(it.gcode_meta.get("material") or "?") for it in items})
    qty = sum(int(it.quantity or 1) for it in items)
    multi_color = len(materials) > 1

    # Recent commercial quotes for context
    recent = (
        await session.execute(
            select(Quote)
            .where(
                Quote.kind == QuoteKind.COMMERCIAL.value,
                Quote.status.in_(
                    [
                        QuoteStatus.APROVADO.value,
                        QuoteStatus.PRODUZIDO.value,
                        QuoteStatus.ENTREGUE.value,
                    ]
                ),
            )
            .order_by(Quote.created_at.desc())
            .limit(10)
        )
    ).scalars().all()

    history_lines = [
        f"  - markup {float(q.markup_pct):.0f}%  (status={q.status})"
        for q in recent
    ]
    history = "\n".join(history_lines) or "  (sem histórico ainda)"

    user_prompt = (
        f"Orçamento atual:\n"
        f"  - tempo total de impressão: {total_time/3600:.1f}h\n"
        f"  - filamento total: {total_filament:.1f} m\n"
        f"  - peças: {len(items)} (quantidade total: {qty})\n"
        f"  - materiais: {', '.join(materials)}\n"
        f"  - multi-color: {'sim' if multi_color else 'não'}\n"
        f"  - markup atual definido: {float(quote.markup_pct):.0f}%\n\n"
        f"Histórico de últimos 10 orçamentos comerciais aprovados+:\n{history}\n\n"
        "Recomende um markup percentual. Considere risco (tempo longo, material caro, "
        "multi-color) e o padrão do dono."
    )
    return await call_json(session, system=SYSTEM, user=user_prompt, max_tokens=400)
