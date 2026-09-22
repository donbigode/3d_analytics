"""Helpers compartilhados entre os submódulos de rotas de orçamento.

Movido sem alteração de lógica a partir do antigo `backend/api/routes/quotes.py`.
"""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.schemas.quotes import (
    ConsumptionOut,
    QuoteItemOut,
    QuoteOut,
    QuotePhotoOut,
    QuoteServiceOut,
)
from backend.core.gcode.parser import GcodeMeta
from backend.core.pricing.quote import (
    ItemInput,
    ServiceLine,
    compute_item_cost,
    compute_quote_total,
)
from backend.core.quote_service import gcode_to_item_input
from backend.infra.db.models import (
    MaterialConsumption,
    MaterialVersion,
    Quote,
    QuoteItem,
    QuotePerson,
    QuotePhoto,
    Settings,
    Spool,
)
from backend.infra.db.repos import quote as quote_repo


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _get_settings_row(session: AsyncSession) -> Settings:
    s = await session.get(Settings, 1)
    if s is None:
        # Build a transient row with the documented defaults so cost computation
        # never sees None for numeric fields.
        s = Settings(
            id=1,
            energy_kwh_price=Decimal("0.95"),
            printer_power_w=Decimal("150"),
            printer_depreciation_per_hour=Decimal("0"),
            currency="BRL",
            business_name="Sua Marca",
            business_tagline=None,
            logo_path=None,
            brand_color_primary="#111827",
            stalled_quote_alert_days=7,
            low_spool_threshold_g=Decimal("100"),
            printer_hours_per_day=22,
        )
    return s


async def _build_item_input(
    session: AsyncSession, it: QuoteItem, settings_row: Settings
) -> ItemInput | None:
    """Return ItemInput for cost calc, or None if the item has no resolved material (pending)."""
    if not it.material_version_id:
        return None
    mv = await session.get(MaterialVersion, it.material_version_id)
    if not mv:
        return None
    deprec = it.depreciation_rate_override or settings_row.printer_depreciation_per_hour
    failure = it.failure_rate_override or mv.failure_rate_pct
    waste_pct = (
        mv.multi_color_waste_pct if it.is_multi_color else mv.single_color_waste_pct
    ) or Decimal("0")
    meta = GcodeMeta(
        time_s=float(it.gcode_meta.get("time_s") or 0),
        filament_m=float(it.gcode_meta.get("filament_m") or 0),
        material=it.gcode_meta.get("material"),
        machine=it.gcode_meta.get("machine"),
    )
    return gcode_to_item_input(
        meta=meta,
        density=mv.density_g_cm3,
        price_per_kg=mv.price_per_kg_ref,
        power_w=settings_row.printer_power_w,
        kwh_price=settings_row.energy_kwh_price,
        depreciation_per_hour=deprec,
        failure_pct=failure,
        quantity=it.quantity,
        maintenance_per_hour=settings_row.printer_maintenance_per_hour or Decimal("0"),
        waste_pct=waste_pct,
        filament_g=(float(it.gcode_meta["filament_g"])
                    if it.gcode_meta.get("filament_g") not in (None, "") else None),
    )


def _photo_out(p: QuotePhoto) -> QuotePhotoOut:
    return QuotePhotoOut(
        id=str(p.id),
        quote_item_id=str(p.quote_item_id) if p.quote_item_id else None,
        url=f"/quotes/photos/{p.id}/raw",
        width=p.width,
        height=p.height,
        sort_order=p.sort_order,
    )


def _spool_label(sp: Spool) -> str:
    """Mesmo formato (tipo · fabricante · cor) usado no seletor da tela de
    produzir, para a pessoa reconhecer a bobina nos dois lugares.

    ``remaining_grams`` fica de fora — muda com o tempo e o consumo é um
    registro histórico. ``purchased_at`` e ``purchased_from``, ao contrário,
    são fixos desde a criação da bobina (como no seletor de produzir) e
    servem de desambiguador legível para quem comprou a bobina, quando duas
    bobinas têm o mesmo tipo/fabricante/cor — um sufixo de UUID não serviria
    porque não aparece em lugar nenhum da tela de produzir."""
    partes = [sp.material_type]
    if sp.manufacturer:
        partes.append(sp.manufacturer)
    if sp.color:
        partes.append(sp.color)
    if sp.purchased_from:
        partes.append(sp.purchased_from)
    if sp.purchased_at:
        partes.append(f"{sp.purchased_at.month:02d}/{sp.purchased_at.year}")
    return " · ".join(partes)


async def _consumptions_map(
    session: AsyncSession, item_ids: list[UUID]
) -> dict[UUID, list[ConsumptionOut]]:
    """Consumos de todos os itens do orçamento numa query só — buscar por
    item reintroduziria o N+1 que a Spec 2 acabou de tirar do contábil."""
    if not item_ids:
        return {}
    rows = (
        await session.execute(
            select(MaterialConsumption, Spool)
            .join(Spool, Spool.id == MaterialConsumption.spool_id)
            .where(MaterialConsumption.quote_item_id.in_(item_ids))
            .order_by(MaterialConsumption.consumed_at)
        )
    ).all()
    out: dict[UUID, list[ConsumptionOut]] = {}
    for cons, sp in rows:
        out.setdefault(cons.quote_item_id, []).append(
            ConsumptionOut(
                spool_id=str(sp.id),
                spool_label=_spool_label(sp),
                material_type=sp.material_type,
                color=sp.color,
                manufacturer=sp.manufacturer,
                grams_used=cons.grams_used,
                unit_cost_snapshot=cons.unit_cost_snapshot,
                # unit_cost_snapshot é o custo por grama congelado no momento
                # da baixa — não recalcular pelo preço atual da bobina.
                # Sem quantize aqui: backend/core/accounting/cost.py soma os
                # consumos sem arredondar linha a linha e só arredonda o
                # agregado (padrão _q2 usado em dre.py/facts.py/
                # profitability.py). Arredondar por linha faria o total do
                # painel divergir do CPV do DRE em peças com 2+ consumos.
                # O arredondamento é responsabilidade de quem exibe.
                custo_total=cons.grams_used * cons.unit_cost_snapshot,
                consumed_at=cons.consumed_at,
            )
        )
    return out


async def _quote_out(session: AsyncSession, q: Quote) -> QuoteOut:
    s = await _get_settings_row(session)
    items = await quote_repo.list_items(session, q.id)
    services = await quote_repo.list_services(session, q.id)

    item_inputs: list[ItemInput] = []
    item_subtotals: list[Decimal] = []
    pending_items = 0
    for it in items:
        ii = await _build_item_input(session, it, s)
        if ii is None:
            pending_items += 1
            item_subtotals.append(Decimal("0"))
        else:
            item_inputs.append(ii)
            item_subtotals.append(compute_item_cost(ii))

    service_lines = [
        ServiceLine(quantity=sv.quantity, rate=sv.rate, is_material=False)
        for sv in services
    ]
    services_cost = sum((sv.quantity * sv.rate for sv in services), Decimal(0))
    items_cost = sum(item_subtotals, Decimal(0))
    cost = items_cost + services_cost
    total = compute_quote_total(
        items=item_inputs,
        services=service_lines,
        markup_pct=q.markup_pct,
        min_charge=q.min_charge,
    )

    photos = (await session.execute(
        select(QuotePhoto)
        .where(QuotePhoto.quote_id == q.id)
        .order_by(QuotePhoto.sort_order, QuotePhoto.created_at)
    )).scalars().all()
    cover_photos = [_photo_out(p) for p in photos if p.quote_item_id is None]
    photos_by_item: dict[str, list[QuotePhotoOut]] = {}
    for p in photos:
        if p.quote_item_id is not None:
            photos_by_item.setdefault(str(p.quote_item_id), []).append(_photo_out(p))

    person_rows = (await session.execute(
        select(QuotePerson.person_id).where(QuotePerson.quote_id == q.id)
    )).scalars().all()
    person_ids = [str(pid) for pid in person_rows]

    consumptions_by_item = await _consumptions_map(session, [it.id for it in items])

    items_out = [
        QuoteItemOut(
            id=str(it.id),
            name=it.name,
            filename=it.filename,
            gcode_meta=it.gcode_meta,
            quantity=it.quantity,
            subtotal=item_subtotals[idx].quantize(Decimal("0.01")),
            material_id=str(it.material_version_id) if it.material_version_id else None,
            is_multi_color=bool(it.is_multi_color),
            material_pending=(it.material_version_id is None),
            pending_material_code=(
                (it.gcode_meta.get("material") if it.material_version_id is None else None)
            ),
            model_source_url=it.model_source_url,
            model_source_author=it.model_source_author,
            model_source_license=it.model_source_license,
            photos=photos_by_item.get(str(it.id), []),
            consumptions=consumptions_by_item.get(it.id, []),
        )
        for idx, it in enumerate(items)
    ]
    services_out = [
        QuoteServiceOut(
            id=str(sv.id),
            service_id=str(sv.service_id),
            quantity=sv.quantity,
            rate=sv.rate,
            subtotal=(sv.quantity * sv.rate).quantize(Decimal("0.01")),
        )
        for sv in services
    ]

    return QuoteOut(
        id=str(q.id),
        seq=q.seq,
        kind=q.kind,
        client_id=str(q.client_id) if q.client_id else None,
        status=q.status,
        markup_pct=q.markup_pct,
        min_charge=q.min_charge,
        retail_mode=q.retail_mode,
        notes=q.notes,
        items=items_out,
        services=services_out,
        cost=cost.quantize(Decimal("0.01")),
        total=total.quantize(Decimal("0.01")),
        pending_items=pending_items,
        created_at=q.created_at,
        finalized_at=q.finalized_at,
        approved_at=q.approved_at,
        produced_at=q.produced_at,
        delivered_at=q.delivered_at,
        photos=cover_photos,
        person_ids=person_ids,
    )


async def _assert_materials_resolved(session: AsyncSession, q: Quote) -> None:
    """Block finalizing/producing a quote that still has items whose material
    couldn't be matched to a registered ``MaterialVersion`` — without it we
    can't compute filament grams (and therefore can't debit the spool)."""
    pending = await session.scalar(
        select(func.count(QuoteItem.id)).where(
            QuoteItem.quote_id == q.id,
            QuoteItem.material_version_id.is_(None),
        )
    )
    if pending and pending > 0:
        codes = await session.execute(
            select(QuoteItem.gcode_meta).where(
                QuoteItem.quote_id == q.id,
                QuoteItem.material_version_id.is_(None),
            )
        )
        pending_codes = {
            (m or {}).get("material") or "?" for m in codes.scalars()
        }
        raise HTTPException(
            409,
            f"there are {pending} item(s) with unregistered materials: "
            f"{', '.join(sorted(pending_codes))}. Register them and resolve each item before finalizing.",
        )


async def _cycle_context_and_grams(session: AsyncSession, q: Quote):
    """Snapshot per-piece context (material/colour/manufacturer + print
    characteristics) and the total grams consumed in the current cycle, so the
    ProductionEvent survives even if quote/spools change later."""
    items = (
        await session.execute(select(QuoteItem).where(QuoteItem.quote_id == q.id))
    ).scalars().all()
    ctx: list[dict] = []
    grams = Decimal("0")
    for it in items:
        meta = it.gcode_meta or {}
        cons = (
            await session.execute(
                select(MaterialConsumption).where(
                    MaterialConsumption.quote_item_id == it.id
                )
            )
        ).scalars().all()
        sp = None
        if cons:
            sp = await session.get(Spool, cons[-1].spool_id)
            grams += sum((c.grams_used or Decimal("0")) for c in cons)
        ctx.append(
            {
                "name": it.name,
                "material_type": (sp.material_type if sp else meta.get("material")),
                "color": (sp.color if sp else None),
                "manufacturer": (sp.manufacturer if sp else None),
                "filament_m": meta.get("filament_m"),
                "time_s": meta.get("time_s"),
                "is_multi_color": bool(getattr(it, "is_multi_color", False)),
                "machine": meta.get("machine"),
                "model_source_url": getattr(it, "model_source_url", None),
            }
        )
    return ctx, grams
