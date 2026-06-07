import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import db_session, require_user
from backend.api.schemas.quotes import (
    ProduceRequest,
    QuoteCreate,
    QuoteItemOut,
    QuoteItemUpdate,
    QuoteOut,
    QuoteServiceOut,
    QuoteUpdate,
    ServiceLineCreate,
)
from backend.core.gcode.parser import GcodeMeta, parse_gcode_metadata
from backend.core.models import (
    QuoteKind,
    QuoteStatus,
    ServiceKind,
    SpoolStatus,
)
from backend.core.pricing.quote import (
    ItemInput,
    ServiceLine,
    compute_item_cost,
    compute_quote_total,
)
from backend.core.quote_service import gcode_to_item_input, grams_for_item
from backend.infra.db.models import (
    Client,
    MaterialConsumption,
    MaterialVersion,
    Quote,
    QuoteItem,
    QuoteService,
    Service,
    Settings,
    Spool,
    User,
)
from backend.infra.db.repos import material as material_repo
from backend.infra.db.repos import quote as quote_repo
from backend.infra.pdf.render import render_quote_pdf
from backend.infra.storage.gcodes import save_gcode
from backend.settings import get_settings as get_app_settings

router = APIRouter()


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
    )


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

    items_out = [
        QuoteItemOut(
            id=str(it.id),
            name=it.name,
            filename=it.filename,
            gcode_meta=it.gcode_meta,
            quantity=it.quantity,
            subtotal=item_subtotals[idx].quantize(Decimal("0.01")),
            material_pending=(it.material_version_id is None),
            pending_material_code=(
                (it.gcode_meta.get("material") if it.material_version_id is None else None)
            ),
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
        kind=q.kind,
        client_id=str(q.client_id) if q.client_id else None,
        status=q.status,
        markup_pct=q.markup_pct,
        min_charge=q.min_charge,
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
    )


# ---------- CRUD ----------

@router.post("", response_model=QuoteOut, status_code=201)
async def create_quote(
    payload: QuoteCreate,
    user: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    q = Quote(
        kind=payload.kind,
        user_id=user.id,
        status=QuoteStatus.DRAFT,
        markup_pct=payload.markup_pct,
        min_charge=payload.min_charge,
        notes=payload.notes,
        client_id=UUID(payload.client_id) if payload.client_id else None,
    )
    session.add(q)
    await session.commit()
    await session.refresh(q)
    return await _quote_out(session, q)


@router.get("", response_model=list[QuoteOut])
async def list_quotes(
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
    status: QuoteStatus | None = Query(None),
    kind: QuoteKind | None = Query(None),
    client_id: str | None = Query(None),
):
    stmt = select(Quote).order_by(Quote.created_at.desc())
    if status:
        stmt = stmt.where(Quote.status == status)
    if kind:
        stmt = stmt.where(Quote.kind == kind)
    if client_id:
        stmt = stmt.where(Quote.client_id == UUID(client_id))
    res = await session.execute(stmt)
    out = []
    for q in res.scalars():
        out.append(await _quote_out(session, q))
    return out


@router.get("/{quote_id}", response_model=QuoteOut)
async def get_quote(
    quote_id: UUID,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    q = await session.get(Quote, quote_id)
    if not q:
        raise HTTPException(404)
    return await _quote_out(session, q)


@router.put("/{quote_id}", response_model=QuoteOut)
async def update_quote(
    quote_id: UUID,
    payload: QuoteUpdate,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    q = await session.get(Quote, quote_id)
    if not q:
        raise HTTPException(404)
    if q.status != QuoteStatus.DRAFT:
        raise HTTPException(409, "quote not editable")
    for k, v in payload.model_dump(exclude_unset=True).items():
        if k == "client_id" and v is not None:
            v = UUID(v)
        setattr(q, k, v)
    await session.commit()
    return await _quote_out(session, q)


# ---------- Items ----------

@router.post("/{quote_id}/items", response_model=QuoteOut, status_code=201)
async def add_item(
    quote_id: UUID,
    file: UploadFile = File(...),
    name: str = Form(...),
    quantity: int = Form(1),
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    q = await session.get(Quote, quote_id)
    if not q:
        raise HTTPException(404)
    if q.status != QuoteStatus.DRAFT:
        raise HTTPException(409, "quote not editable")

    content = await file.read()
    try:
        with tempfile.NamedTemporaryFile(suffix=".gcode", delete=True) as tf:
            tf.write(content)
            tf.flush()
            meta = parse_gcode_metadata(Path(tf.name))
    except ValueError as e:
        raise HTTPException(400, str(e))

    material_code = meta.material or "PLA"
    mv = await material_repo.current(session, material_code)
    # If material not registered, item is accepted with material_version_id=NULL
    # (pending). User can resolve via PUT /quotes/{id}/items/{item_id} after
    # registering the material. Finalize is blocked while there are pending items.

    rel_path = save_gcode(q.id, file.filename or "upload.gcode", content)
    item = QuoteItem(
        quote_id=q.id,
        name=name,
        filename=rel_path,
        gcode_meta={
            "time_s": meta.time_s,
            "filament_m": meta.filament_m,
            "material": meta.material,
            "machine": meta.machine,
        },
        material_version_id=mv.id if mv else None,
        quantity=quantity,
    )
    session.add(item)
    await session.commit()
    await session.refresh(q)
    return await _quote_out(session, q)


@router.put("/{quote_id}/items/{item_id}", response_model=QuoteOut)
async def update_item(
    quote_id: UUID,
    item_id: UUID,
    payload: QuoteItemUpdate,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    q = await session.get(Quote, quote_id)
    if not q:
        raise HTTPException(404)
    if q.status != QuoteStatus.DRAFT:
        raise HTTPException(409, "quote not editable")
    it = await session.get(QuoteItem, item_id)
    if not it or it.quote_id != quote_id:
        raise HTTPException(404)
    if payload.name is not None:
        it.name = payload.name
    if payload.quantity is not None:
        if payload.quantity < 1:
            raise HTTPException(400, "quantity must be >= 1")
        it.quantity = payload.quantity
    if payload.material_code is not None:
        mv = await material_repo.current(session, payload.material_code)
        if not mv:
            raise HTTPException(400, f"material {payload.material_code} not registered")
        it.material_version_id = mv.id
        # also update gcode_meta.material to reflect the chosen code, so the
        # next time the user looks at the item the badge is gone
        meta = dict(it.gcode_meta or {})
        meta["material"] = payload.material_code
        it.gcode_meta = meta
    await session.commit()
    return await _quote_out(session, q)


@router.delete("/{quote_id}/items/{item_id}", response_model=QuoteOut)
async def delete_item(
    quote_id: UUID,
    item_id: UUID,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    q = await session.get(Quote, quote_id)
    if not q:
        raise HTTPException(404)
    if q.status != QuoteStatus.DRAFT:
        raise HTTPException(409, "quote not editable")
    it = await session.get(QuoteItem, item_id)
    if not it or it.quote_id != quote_id:
        raise HTTPException(404)
    await session.delete(it)
    await session.commit()
    return await _quote_out(session, q)


# ---------- Services ----------

@router.post("/{quote_id}/services", response_model=QuoteOut, status_code=201)
async def add_service(
    quote_id: UUID,
    payload: ServiceLineCreate,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    q = await session.get(Quote, quote_id)
    if not q:
        raise HTTPException(404)
    if q.status != QuoteStatus.DRAFT:
        raise HTTPException(409, "quote not editable")
    svc = await session.get(Service, UUID(payload.service_id))
    if not svc:
        raise HTTPException(404, "service not found")
    if q.kind == QuoteKind.PERSONAL and svc.kind == ServiceKind.LABOR:
        raise HTTPException(400, "labor services not allowed on personal quotes")
    qs = QuoteService(
        quote_id=q.id,
        service_id=svc.id,
        quantity=payload.quantity,
        rate=payload.rate if payload.rate is not None else svc.default_rate,
    )
    session.add(qs)
    await session.commit()
    return await _quote_out(session, q)


@router.delete("/{quote_id}/services/{qs_id}", response_model=QuoteOut)
async def delete_service(
    quote_id: UUID,
    qs_id: UUID,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    q = await session.get(Quote, quote_id)
    if not q:
        raise HTTPException(404)
    if q.status != QuoteStatus.DRAFT:
        raise HTTPException(409, "quote not editable")
    qs = await session.get(QuoteService, qs_id)
    if not qs or qs.quote_id != quote_id:
        raise HTTPException(404)
    await session.delete(qs)
    await session.commit()
    return await _quote_out(session, q)


# ---------- Transitions ----------

@router.post("/{quote_id}/transitions/finalize", response_model=QuoteOut)
async def t_finalize(
    quote_id: UUID,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    q = await session.get(Quote, quote_id)
    if not q:
        raise HTTPException(404)
    if q.status != QuoteStatus.DRAFT:
        raise HTTPException(409, "quote is not in draft")
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
    q.finalized_at = _now()
    if q.kind == QuoteKind.PERSONAL:
        q.status = QuoteStatus.PRODUZIDO
        q.produced_at = _now()
    else:
        q.status = QuoteStatus.ORCADO
    await session.commit()
    return await _quote_out(session, q)


@router.post("/{quote_id}/transitions/approve", response_model=QuoteOut)
async def t_approve(
    quote_id: UUID,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    q = await session.get(Quote, quote_id)
    if not q:
        raise HTTPException(404)
    if q.kind != QuoteKind.COMMERCIAL:
        raise HTTPException(400, "only commercial quotes can be approved")
    if q.status != QuoteStatus.ORCADO:
        raise HTTPException(409, "quote is not in orcado")
    q.status = QuoteStatus.APROVADO
    q.approved_at = _now()
    await session.commit()
    return await _quote_out(session, q)


@router.post("/{quote_id}/transitions/produce", response_model=QuoteOut)
async def t_produce(
    quote_id: UUID,
    payload: ProduceRequest,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    q = await session.get(Quote, quote_id)
    if not q:
        raise HTTPException(404)
    if q.kind != QuoteKind.COMMERCIAL:
        raise HTTPException(400, "only commercial quotes flow through produce")
    if q.status != QuoteStatus.APROVADO:
        raise HTTPException(409, "quote must be aprovado before produce")

    for assign in payload.consumption:
        it = await session.get(QuoteItem, UUID(assign.quote_item_id))
        sp = await session.get(Spool, UUID(assign.spool_id))
        if not it or it.quote_id != q.id or not sp:
            raise HTTPException(400, "invalid assignment")
        mv = await session.get(MaterialVersion, it.material_version_id)
        grams = grams_for_item(it.gcode_meta, mv.density_g_cm3, it.quantity)
        if sp.remaining_grams < grams:
            raise HTTPException(409, f"spool {sp.id} has insufficient grams")
        sp.remaining_grams = sp.remaining_grams - grams
        if sp.remaining_grams <= 0:
            sp.status = SpoolStatus.EMPTY
        unit_cost = sp.purchased_price / sp.initial_grams
        session.add(
            MaterialConsumption(
                quote_item_id=it.id,
                spool_id=sp.id,
                grams_used=grams,
                unit_cost_snapshot=unit_cost,
            )
        )
    q.status = QuoteStatus.PRODUZIDO
    q.produced_at = _now()
    await session.commit()
    return await _quote_out(session, q)


@router.post("/{quote_id}/transitions/deliver", response_model=QuoteOut)
async def t_deliver(
    quote_id: UUID,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    q = await session.get(Quote, quote_id)
    if not q:
        raise HTTPException(404)
    if q.kind != QuoteKind.COMMERCIAL:
        raise HTTPException(400, "only commercial quotes can be delivered")
    if q.status != QuoteStatus.PRODUZIDO:
        raise HTTPException(409, "quote must be produzido before deliver")
    q.status = QuoteStatus.ENTREGUE
    q.delivered_at = _now()
    await session.commit()
    return await _quote_out(session, q)


@router.post("/{quote_id}/transitions/cancel", response_model=QuoteOut)
async def t_cancel(
    quote_id: UUID,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    q = await session.get(Quote, quote_id)
    if not q:
        raise HTTPException(404)
    if q.status in (QuoteStatus.ENTREGUE, QuoteStatus.CANCELADO):
        raise HTTPException(409, "quote already finalized")
    q.status = QuoteStatus.CANCELADO
    q.cancelled_at = _now()
    await session.commit()
    return await _quote_out(session, q)


# ---------- PDF ----------

@router.get("/{quote_id}/pdf")
async def get_pdf(
    quote_id: UUID,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    q = await session.get(Quote, quote_id)
    if not q:
        raise HTTPException(404)
    s = await _get_settings_row(session)

    items = await quote_repo.list_items(session, q.id)
    services = await quote_repo.list_services(session, q.id)

    item_inputs: list[ItemInput] = []
    item_subtotals: list[Decimal] = []
    for it in items:
        ii = await _build_item_input(session, it, s)
        if ii is None:
            item_subtotals.append(Decimal("0"))
        else:
            item_inputs.append(ii)
            item_subtotals.append(compute_item_cost(ii))
    service_lines = [
        ServiceLine(quantity=sv.quantity, rate=sv.rate, is_material=False)
        for sv in services
    ]
    services_cost = sum((sv.quantity * sv.rate for sv in services), Decimal(0))
    cost = sum(item_subtotals, Decimal(0)) + services_cost
    total = compute_quote_total(
        items=item_inputs,
        services=service_lines,
        markup_pct=q.markup_pct,
        min_charge=q.min_charge,
    )

    client_name = None
    if q.client_id:
        c = await session.get(Client, q.client_id)
        client_name = c.name if c else None

    item_dicts = []
    for idx, it in enumerate(items):
        item_dicts.append(
            {
                "name": it.name,
                "filament_m": it.gcode_meta.get("filament_m") or 0,
                "time_s": it.gcode_meta.get("time_s") or 0,
                "qty": it.quantity,
                "subtotal": float(item_subtotals[idx]),
            }
        )
    service_dicts = []
    for sv in services:
        svc = await session.get(Service, sv.service_id)
        service_dicts.append(
            {
                "name": svc.name if svc else "—",
                "qty": float(sv.quantity),
                "rate": float(sv.rate),
                "subtotal": float(sv.quantity * sv.rate),
            }
        )

    logo_url = None
    if s.logo_path:
        try:
            logo_url = (Path(get_app_settings().storage_dir) / s.logo_path).as_uri()
        except Exception:
            logo_url = None

    data = {
        "business_name": s.business_name,
        "business_tagline": s.business_tagline,
        "logo_url": logo_url,
        "brand_color": s.brand_color_primary,
        "currency": s.currency,
        "now": _now().strftime("%Y-%m-%d %H:%M"),
        "quote": {
            "id": str(q.id)[:8],
            "kind": q.kind,
            "status": q.status,
            "client": client_name,
        },
        "items": item_dicts,
        "services": service_dicts,
        "totals": {
            "cost": float(cost),
            "markup_pct": float(q.markup_pct),
            "min_charge": float(q.min_charge),
            "total": float(total),
        },
    }
    pdf = render_quote_pdf(data)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="quote-{str(q.id)[:8]}.pdf"'
        },
    )
