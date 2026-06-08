"""Explain why a produced quote's real cost differed from its orçado."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.llm_features.runner import call_text
from backend.infra.db.models import (
    MaterialConsumption,
    MaterialVersion,
    Quote,
    QuoteItem,
)


SYSTEM = (
    "Você analisa variâncias de custo orçado vs real em impressão 3D. "
    "Escreve uma explicação em 2-3 frases em português apontando a CAUSA "
    "PRINCIPAL e UMA ação concreta de calibração (ajustar taxa de falha, "
    "atualizar preço do material, reavaliar mão de obra). Sem markdown."
)


async def explain_variance(
    session: AsyncSession, quote: Quote, *, orcado: Decimal, real: Decimal
) -> str:
    items = (
        await session.execute(select(QuoteItem).where(QuoteItem.quote_id == quote.id))
    ).scalars().all()

    by_material: dict[str, dict[str, float]] = {}
    for it in items:
        if not it.material_version_id:
            continue
        mv = await session.get(MaterialVersion, it.material_version_id)
        if not mv:
            continue
        cons = (
            await session.execute(
                select(MaterialConsumption).where(
                    MaterialConsumption.quote_item_id == it.id
                )
            )
        ).scalars().all()
        real_grams = float(sum((c.grams_used for c in cons), Decimal(0)))
        real_cost = float(sum((c.grams_used * c.unit_cost_snapshot for c in cons), Decimal(0)))
        slot = by_material.setdefault(
            mv.material_type,
            {
                "real_grams": 0.0,
                "real_cost": 0.0,
                "catalog_price_per_kg": float(mv.price_per_kg_ref),
                "catalog_failure_pct": float(mv.failure_rate_pct),
            },
        )
        slot["real_grams"] += real_grams
        slot["real_cost"] += real_cost

    mat_lines = [
        f"  - {code}: {data['real_grams']:.0f}g consumidos, "
        f"custo real R${data['real_cost']:.2f}, "
        f"catálogo R${data['catalog_price_per_kg']:.2f}/kg, "
        f"taxa falha cadastrada {data['catalog_failure_pct']:.1f}%"
        for code, data in by_material.items()
    ] or ["  (nenhuma consumption registrada)"]

    diff = float(real - orcado)
    pct = (diff / float(orcado) * 100) if orcado else 0
    user_prompt = (
        f"Resultado do orçamento:\n"
        f"  - orçado: R${float(orcado):.2f}\n"
        f"  - real:   R${float(real):.2f}\n"
        f"  - diferença: {diff:+.2f} ({pct:+.1f}%)\n\n"
        f"Consumo por material:\n" + "\n".join(mat_lines) + "\n\n"
        "Explique a causa principal e dê 1 ação concreta."
    )
    return await call_text(session, system=SYSTEM, user=user_prompt, max_tokens=300)
