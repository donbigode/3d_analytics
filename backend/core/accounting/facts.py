from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.accounting.dre import sale_cpv
from backend.core.pricing.cost import filament_cost
from backend.core.quote_service import effective_grams_per_unit
from backend.infra.db.models import (
    Client, MaterialConsumption, MaterialVersion, QuoteItem, Sale, Spool,
)

_DIAMETER_MM = Decimal("1.75")


def _q2(d: Decimal) -> Decimal:
    return d.quantize(Decimal("0.01"))


async def _item_details(session: AsyncSession, it: QuoteItem) -> dict:
    """Campos por item: material/cor, gramas efetivas, custo de filamento, cor da bobina."""
    material_type = "—"
    cor_material = None
    custo = Decimal(0)
    gramas_total = Decimal(0)
    mv = None
    if it.material_version_id:
        mv = await session.get(MaterialVersion, it.material_version_id)
    filament_m = it.gcode_meta.get("filament_m")
    raw_g = it.gcode_meta.get("filament_g")
    filament_g = float(raw_g) if raw_g not in (None, "") else None
    if mv is not None:
        material_type = mv.material_type
        cor_material = mv.color
        grams_unit = effective_grams_per_unit(
            float(filament_m or 0), filament_g, mv.density_g_cm3, _DIAMETER_MM, Decimal("0")
        )
        gramas_total = grams_unit * Decimal(it.quantity)
        custo = filament_cost(gramas_total, mv.price_per_kg_ref)

    # cor da bobina consumida (pipe-join de cores distintas)
    cons_rows = (
        await session.execute(
            select(Spool.color)
            .join(MaterialConsumption, MaterialConsumption.spool_id == Spool.id)
            .where(MaterialConsumption.quote_item_id == it.id)
        )
    ).scalars().all()
    cores = sorted({c for c in cons_rows if c})
    cor_bobina = " | ".join(cores) if cores else None

    return {
        "item_id": str(it.id),
        "nome": it.name,
        "quantidade": it.quantity,
        "material_type": material_type,
        "cor_material": cor_material,
        "cor_bobina": cor_bobina,
        "filament_m": float(filament_m) if filament_m not in (None, "") else None,
        "filament_g": filament_g,
        "gramas_total": _q2(gramas_total),
        "custo_filamento_item": _q2(custo),
    }


async def compute_facts(session: AsyncSession, period_from: date, period_to: date) -> list[dict]:
    """Uma linha por (venda confirmada ativa × item do orçamento)."""
    sales = (
        await session.execute(
            select(Sale).where(
                Sale.is_sold.is_(True), Sale.is_stale.is_(False),
                Sale.sold_at.is_not(None),
                Sale.sold_at >= period_from, Sale.sold_at <= period_to,
            )
        )
    ).scalars().all()

    out: list[dict] = []
    for sale in sales:
        receita = sale.confirmed_revenue or Decimal(0)
        cpv = sale_cpv(sale)
        cname = "—"
        if sale.client_id:
            c = await session.get(Client, sale.client_id)
            cname = c.name if c else "—"

        items = (await session.execute(
            select(QuoteItem).where(QuoteItem.quote_id == sale.quote_id))).scalars().all()
        details = [await _item_details(session, it) for it in items]

        total_fcost = sum((d["custo_filamento_item"] for d in details), Decimal(0))
        n = len(details)
        for d in details:
            if total_fcost > 0:
                receita_item = receita * d["custo_filamento_item"] / total_fcost
            elif n > 0:
                receita_item = receita / Decimal(n)
            else:
                receita_item = Decimal(0)
            out.append({
                "sale_id": str(sale.id),
                "quote_id": str(sale.quote_id),
                "quote_kind": sale.quote_kind,
                "cliente": cname,
                "status": sale.quote_status,
                "sold_at": sale.sold_at,
                "is_sold": sale.is_sold,
                "receita_venda": _q2(receita),
                "custos_variaveis_venda": _q2(sale.variable_costs),
                "cpv_venda": _q2(cpv),
                **d,
                "receita_item": _q2(receita_item),
            })
    return out


async def sale_items_label(session: AsyncSession, sale: Sale) -> str:
    """Rótulo pipe dos itens de uma venda: 'Vaso ×2 (Verde) | Suporte ×1 (Azul)'."""
    items = (await session.execute(
        select(QuoteItem).where(QuoteItem.quote_id == sale.quote_id))).scalars().all()
    parts: list[str] = []
    for it in items:
        d = await _item_details(session, it)
        cor = d["cor_bobina"] or d["cor_material"]
        suffix = f" ({cor})" if cor else ""
        parts.append(f"{d['nome']} ×{d['quantidade']}{suffix}")
    return " | ".join(parts)


async def sale_items_label_map(
    session: AsyncSession, quote_ids: list[UUID],
) -> dict[UUID, str]:
    """Versão em lote de `sale_items_label`: mesmo rótulo, três queries no
    total (quote_items, material_versions, spool×consumption) em vez de uma
    por venda + uma por item (o N+1 de `_item_details`).

    Reproduz exatamente a regra de `_item_details`/`sale_items_label`:
    cor = cor da bobina consumida (pipe-join de cores distintas, ordenadas)
    ou, na ausência dela, a cor do material do orçamento; item sem nenhuma
    das duas não leva sufixo. A ordem dos itens dentro de cada orçamento
    segue a ordem de retorno da query (mesma ordem física que a consulta
    por-orçamento original já produzia, sem ORDER BY explícito em nenhuma
    das duas)."""
    if not quote_ids:
        return {}

    items = (
        await session.execute(select(QuoteItem).where(QuoteItem.quote_id.in_(quote_ids)))
    ).scalars().all()
    if not items:
        return {qid: "" for qid in quote_ids}

    mv_ids = [it.material_version_id for it in items if it.material_version_id]
    cor_material_por_mv: dict[UUID, str | None] = dict(
        (await session.execute(
            select(MaterialVersion.id, MaterialVersion.color).where(MaterialVersion.id.in_(mv_ids))
        )).all()
    ) if mv_ids else {}

    item_ids = [it.id for it in items]
    cons_rows = (
        await session.execute(
            select(MaterialConsumption.quote_item_id, Spool.color)
            .join(Spool, MaterialConsumption.spool_id == Spool.id)
            .where(MaterialConsumption.quote_item_id.in_(item_ids))
        )
    ).all()
    cores_por_item: dict[UUID, set[str]] = {}
    for item_id, cor in cons_rows:
        if cor:
            cores_por_item.setdefault(item_id, set()).add(cor)

    partes_por_quote: dict[UUID, list[str]] = {}
    for it in items:
        cores = cores_por_item.get(it.id)
        cor_bobina = " | ".join(sorted(cores)) if cores else None
        cor_material = cor_material_por_mv.get(it.material_version_id) if it.material_version_id else None
        cor = cor_bobina or cor_material
        suffix = f" ({cor})" if cor else ""
        partes_por_quote.setdefault(it.quote_id, []).append(f"{it.name} ×{it.quantity}{suffix}")

    return {qid: " | ".join(partes_por_quote.get(qid, [])) for qid in quote_ids}
