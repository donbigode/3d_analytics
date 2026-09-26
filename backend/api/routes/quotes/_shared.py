"""Helpers compartilhados entre os submódulos de rotas de orçamento.

Movido sem alteração de lógica a partir do antigo `backend/api/routes/quotes.py`.
"""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.schemas.quotes import (
    ConsumptionOut,
    QuoteItemFilamentOut,
    QuoteItemOut,
    QuoteOut,
    QuotePhotoOut,
    QuoteServiceOut,
)
from backend.core.gcode.parser import GcodeMeta
from backend.core.pricing.quote import (
    FilamentLine,
    ItemInput,
    ServiceLine,
    compute_item_cost,
    compute_quote_total,
)
from backend.core.quote_service import gcode_to_item_input
from backend.core.quotes.filaments import grams_for_line, waste_for_line
from backend.infra.db.models import (
    MaterialConsumption,
    MaterialVersion,
    Quote,
    QuoteItem,
    QuoteItemFilament,
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


async def _filaments_map(
    session: AsyncSession, item_ids: list[UUID]
) -> dict[UUID, list[tuple[QuoteItemFilament, MaterialVersion]]]:
    """Linhas de todos os itens numa query só.

    Buscar por item reintroduziria o N+1 que a Spec 2 acabou de tirar do
    contábil — e aqui seria pior, porque o cálculo de custo percorre os itens.
    """
    if not item_ids:
        return {}
    rows = (
        await session.execute(
            select(QuoteItemFilament, MaterialVersion)
            .join(MaterialVersion, MaterialVersion.id == QuoteItemFilament.material_version_id)
            .where(QuoteItemFilament.quote_item_id.in_(item_ids))
            .order_by(QuoteItemFilament.quote_item_id, QuoteItemFilament.position)
        )
    ).all()
    out: dict[UUID, list[tuple[QuoteItemFilament, MaterialVersion]]] = {}
    for fil, mv in rows:
        out.setdefault(fil.quote_item_id, []).append((fil, mv))
    return out


async def _build_item_input(
    session: AsyncSession,
    it: QuoteItem,
    settings_row: Settings,
    filaments: list[tuple[QuoteItemFilament, MaterialVersion]] | None = None,
) -> ItemInput | None:
    """Return ItemInput for cost calc, or None if the item has no resolved material (pending).

    ``filaments`` vem de ``_filaments_map`` quando o chamador já carregou tudo
    em lote. Quando é ``None``, busca as linhas deste item — caminho usado por
    chamadores de um item só.
    """
    if filaments is None:
        filaments = (await _filaments_map(session, [it.id])).get(it.id, [])

    if not filaments:
        # Item sem linha = material não resolvido (pendente). Mesma semântica
        # que o `if not it.material_version_id` de antes.
        return None

    deprec = it.depreciation_rate_override or settings_row.printer_depreciation_per_hour
    # failure_pct sai do material da PRIMEIRA linha: é uma propriedade da
    # impressão, não de cada cor, e a linha 1 é o material principal do item.
    primeiro_mv = filaments[0][1]
    failure = it.failure_rate_override or primeiro_mv.failure_rate_pct

    linhas: list[FilamentLine] = []
    for fil, mv in filaments:
        waste = waste_for_line(
            fil.grams_unit,
            bool(it.is_multi_color),
            mv.single_color_waste_pct,
            mv.multi_color_waste_pct,
        )
        gramas = grams_for_line(fil.grams_unit, it.gcode_meta or {}, mv.density_g_cm3, waste)
        linhas.append(FilamentLine(grams=gramas, price_per_kg=mv.price_per_kg_ref))

    meta = GcodeMeta(
        time_s=float(it.gcode_meta.get("time_s") or 0),
        filament_m=float(it.gcode_meta.get("filament_m") or 0),
        material=it.gcode_meta.get("material"),
        machine=it.gcode_meta.get("machine"),
    )
    return gcode_to_item_input(
        meta=meta,
        # density/price_per_kg seguem porque a assinatura os exige; com
        # ``filaments`` explícito são ignorados — cada linha traz o seu.
        density=primeiro_mv.density_g_cm3,
        price_per_kg=primeiro_mv.price_per_kg_ref,
        power_w=settings_row.printer_power_w,
        kwh_price=settings_row.energy_kwh_price,
        depreciation_per_hour=deprec,
        failure_pct=failure,
        quantity=it.quantity,
        maintenance_per_hour=settings_row.printer_maintenance_per_hour or Decimal("0"),
        filaments=tuple(linhas),
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

    filaments_by_item = await _filaments_map(session, [it.id for it in items])

    item_inputs: list[ItemInput] = []
    item_subtotals: list[Decimal] = []
    pending_items = 0
    for it in items:
        ii = await _build_item_input(
            session, it, s, filaments=filaments_by_item.get(it.id, [])
        )
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

    # "Pendente" tem UM critério: não tem linha de filamento. É o mesmo que faz
    # `_build_item_input` devolver None e o mesmo que `_assert_materials_resolved`
    # usa. Derivar de `material_version_id` aqui deixaria a tela discordar do
    # custo no instante em que as duas condições divergissem — e a Task 7 traz
    # um caminho de escrita que apaga linhas, o que torna isso alcançável.
    pendentes = {it.id for it in items if not filaments_by_item.get(it.id)}

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
            material_pending=(it.id in pendentes),
            pending_material_code=(
                (it.gcode_meta or {}).get("material") if it.id in pendentes else None
            ),
            model_source_url=it.model_source_url,
            model_source_author=it.model_source_author,
            model_source_license=it.model_source_license,
            photos=photos_by_item.get(str(it.id), []),
            filaments=[
                QuoteItemFilamentOut(
                    id=str(fil.id),
                    material_id=str(mv.id),
                    material_name=mv.name,
                    material_color=mv.color,
                    grams_unit=fil.grams_unit,
                    position=fil.position,
                )
                for fil, mv in filaments_by_item.get(it.id, [])
            ],
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
    can't compute filament grams (and therefore can't debit the spool).

    O critério é "o item tem ao menos uma linha de filamento", não
    ``material_version_id``: é a mesma condição que faz ``_build_item_input``
    devolver ``None``, então não existe orçamento que passe por aqui e depois
    não orce. A mensagem fica igual — é a que a tela mostra.
    """
    items = (
        await session.execute(select(QuoteItem).where(QuoteItem.quote_id == q.id))
    ).scalars().all()
    linhas = await _filaments_map(session, [it.id for it in items])
    pendentes = [it for it in items if not linhas.get(it.id)]
    if pendentes:
        pending_codes = {
            (it.gcode_meta or {}).get("material") or "?" for it in pendentes
        }
        raise HTTPException(
            409,
            f"there are {len(pendentes)} item(s) with unregistered materials: "
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
