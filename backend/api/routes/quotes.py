import logging
import tempfile
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from uuid import UUID

logger = logging.getLogger(__name__)

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
            material_id=str(it.material_version_id) if it.material_version_id else None,
            is_multi_color=bool(it.is_multi_color),
            material_pending=(it.material_version_id is None),
            pending_material_code=(
                (it.gcode_meta.get("material") if it.material_version_id is None else None)
            ),
            model_source_url=it.model_source_url,
            model_source_author=it.model_source_author,
            model_source_license=it.model_source_license,
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
    updates = payload.model_dump(exclude_unset=True)
    # ``retail_mode`` is a presentation toggle (which PDF layout to use),
    # so it stays editable after finalize. Every other field locks the
    # moment the quote leaves draft.
    presentation_only = {"retail_mode"}
    financial_updates = {k: v for k, v in updates.items() if k not in presentation_only}
    if financial_updates and q.status != QuoteStatus.DRAFT:
        raise HTTPException(409, "quote not editable")
    for k, v in updates.items():
        if k == "client_id" and v is not None:
            v = UUID(v)
        setattr(q, k, v)
    await session.commit()
    return await _quote_out(session, q)


# ---------- Items ----------

@router.post("/{quote_id}/items", response_model=QuoteOut, status_code=201)
async def add_item(
    quote_id: UUID,
    name: str = Form(...),
    file: UploadFile | None = File(None),
    quantity: int = Form(1),
    model_source_url: str | None = Form(None),
    model_source_author: str | None = Form(None),
    model_source_license: str | None = Form(None),
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    q = await session.get(Quote, quote_id)
    if not q:
        raise HTTPException(404)
    if q.status != QuoteStatus.DRAFT:
        raise HTTPException(409, "quote not editable")

    rel_path: str | None = None
    meta = GcodeMeta(time_s=0.0, filament_m=0.0, material=None, machine=None)
    if file is not None and file.filename:
        content = await file.read()
        if content:
            # Parse is best-effort: when the slicer dialect isn't recognised we
            # still accept the file and let the user fill in time/filament
            # manually via the inline editor. Rejecting outright would leave
            # them stuck with no path to enter the data.
            try:
                with tempfile.NamedTemporaryFile(suffix=".gcode", delete=True) as tf:
                    tf.write(content)
                    tf.flush()
                    meta = parse_gcode_metadata(Path(tf.name))
            except ValueError as exc:
                logger.info("gcode parse fallback for quote %s: %s", quote_id, exc)
            rel_path = save_gcode(q.id, file.filename or "upload.gcode", content)

    material_type = meta.material or "PLA"
    # Auto-resolve only when exactly one current material matches the polymer
    # type. With multiple manufacturers/colors registered, leave the item
    # pending so the user picks one explicitly.
    mv = await material_repo.auto_resolve_for_gcode(session, material_type)

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
        model_source_url=model_source_url or None,
        model_source_author=model_source_author or None,
        model_source_license=model_source_license or None,
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
    if payload.material_id is not None:
        try:
            mv = await material_repo.get_by_id(session, UUID(payload.material_id))
        except ValueError:
            raise HTTPException(400, "material_id must be a valid UUID")
        if not mv:
            raise HTTPException(400, "material not found")
        it.material_version_id = mv.id
        meta = dict(it.gcode_meta or {})
        meta["material"] = mv.material_type
        it.gcode_meta = meta
    elif payload.material_code is not None:
        # Back-compat: auto-resolve by polymer type when unique.
        mv = await material_repo.auto_resolve_for_gcode(session, payload.material_code)
        if not mv:
            raise HTTPException(
                400,
                f"cannot uniquely resolve material '{payload.material_code}' "
                "(zero or multiple registered) — send material_id instead",
            )
        it.material_version_id = mv.id
        meta = dict(it.gcode_meta or {})
        meta["material"] = payload.material_code
        it.gcode_meta = meta
    if payload.time_s is not None:
        if payload.time_s < 0:
            raise HTTPException(400, "time_s must be >= 0")
        meta = dict(it.gcode_meta or {})
        meta["time_s"] = float(payload.time_s)
        it.gcode_meta = meta
    if payload.filament_m is not None:
        if payload.filament_m < 0:
            raise HTTPException(400, "filament_m must be >= 0")
        meta = dict(it.gcode_meta or {})
        meta["filament_m"] = float(payload.filament_m)
        it.gcode_meta = meta
    if payload.is_multi_color is not None:
        it.is_multi_color = bool(payload.is_multi_color)
    if payload.model_source_url is not None:
        it.model_source_url = payload.model_source_url or None
    if payload.model_source_author is not None:
        it.model_source_author = payload.model_source_author or None
    if payload.model_source_license is not None:
        it.model_source_license = payload.model_source_license or None
    await session.commit()
    return await _quote_out(session, q)


@router.post("/{quote_id}/items/{item_id}/reparse", response_model=QuoteOut)
async def reparse_item(
    quote_id: UUID,
    item_id: UUID,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    """Re-run the gcode parser over the stored file and replace meta.

    Useful when the parser has been improved since the item was created —
    or when the user just wants to undo a manual override and pull values
    back from the file.
    """
    q = await session.get(Quote, quote_id)
    if not q:
        raise HTTPException(404)
    if q.status != QuoteStatus.DRAFT:
        raise HTTPException(409, "quote not editable")
    it = await session.get(QuoteItem, item_id)
    if not it or it.quote_id != quote_id:
        raise HTTPException(404)
    if not it.filename:
        raise HTTPException(409, "esta peça não tem gcode anexado para reanálise")
    full_path = Path(get_app_settings().storage_dir) / it.filename
    if not full_path.exists():
        raise HTTPException(410, "arquivo gcode original não está mais no disco")
    meta = parse_gcode_metadata(full_path)
    it.gcode_meta = {
        "time_s": meta.time_s,
        "filament_m": meta.filament_m,
        "material": meta.material,
        "machine": meta.machine,
    }
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


@router.post("/{quote_id}/transitions/finalize", response_model=QuoteOut)
async def t_finalize(
    quote_id: UUID,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    q = await session.get(Quote, quote_id)
    if not q:
        raise HTTPException(404)
    # Personal projects skip the commercial pipeline and go straight to
    # production — but production debits the stock the user selects, so they
    # finalize through `produce` (which also stamps finalized_at), not here.
    if q.kind == QuoteKind.PERSONAL:
        raise HTTPException(
            400,
            "personal quotes are produced directly via the produce transition "
            "(select the spool for each item)",
        )
    if q.status != QuoteStatus.DRAFT:
        raise HTTPException(409, "quote is not in draft")
    await _assert_materials_resolved(session, q)
    q.finalized_at = _now()
    q.status = QuoteStatus.ORCADO
    await session.commit()
    return await _quote_out(session, q)


@router.post("/{quote_id}/transitions/reopen", response_model=QuoteOut)
async def t_reopen(
    quote_id: UUID,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    """Send a finalized commercial quote back to draft.

    Use case: the client asked for an extra piece after the quote was
    finalized. Rather than create a sibling, we reopen the same one so
    discussion history and analytics stay together. Allowed only from
    ``orcado`` — once a quote is approved/produced/delivered, reopening
    would invalidate downstream events, so we refuse those.
    """
    q = await session.get(Quote, quote_id)
    if not q:
        raise HTTPException(404)
    if q.kind != QuoteKind.COMMERCIAL:
        raise HTTPException(400, "only commercial quotes can be reopened")
    if q.status != QuoteStatus.ORCADO:
        raise HTTPException(
            409, "quote can only be reopened from 'orcado' — current status: " + q.status
        )
    q.status = QuoteStatus.DRAFT
    # Clear the finalize timestamp so the next finalize stamps fresh; the
    # ledger (task #99) will keep the audit history.
    q.finalized_at = None
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
    # Produce = "send to the printer queue": debit the selected spools and move
    # to em_producao (the FIFO in Capacidade, where Concluir/Falhar happen).
    # Commercial enters from aprovado; personal finalize-and-produces from draft.
    # Either kind can re-produce from falhou (a fresh cycle that debits again).
    if q.kind == QuoteKind.COMMERCIAL:
        if q.status not in (QuoteStatus.APROVADO, QuoteStatus.FALHOU):
            raise HTTPException(409, "quote must be aprovado (ou falhou) before produce")
    elif q.kind == QuoteKind.PERSONAL:
        if q.status not in (QuoteStatus.DRAFT, QuoteStatus.FALHOU):
            raise HTTPException(409, "personal quote must be in draft (ou falhou) to produce")
        await _assert_materials_resolved(session, q)
        if q.finalized_at is None:
            q.finalized_at = _now()
    else:
        raise HTTPException(400, "unsupported quote kind for produce")

    for assign in payload.consumption:
        it = await session.get(QuoteItem, UUID(assign.quote_item_id))
        sp = await session.get(Spool, UUID(assign.spool_id))
        if not it or it.quote_id != q.id or not sp:
            raise HTTPException(400, "invalid assignment")
        mv = await session.get(MaterialVersion, it.material_version_id)
        grams = grams_for_item(it.gcode_meta, mv.density_g_cm3, it.quantity)
        if grams <= 0:
            raise HTTPException(
                409,
                f"item '{it.name}' has no filament length (filament_m=0); "
                "reparse the gcode or set the length before producing",
            )
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
    q.status = QuoteStatus.EM_PRODUCAO
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

    # For retail-mode rendering we need each item priced AT THE CLIENT
    # PRICE — cost-share × final total — so the line totals add up to the
    # grand total the customer sees. When the items_cost is zero (every
    # item still pending) we fall back to splitting equally by quantity.
    items_cost = sum(item_subtotals, Decimal("0"))
    # ``total`` already includes services + markup + min_charge.
    items_total_after_markup = total - services_cost
    if items_total_after_markup < 0:
        items_total_after_markup = Decimal("0")

    item_dicts = []
    for idx, it in enumerate(items):
        sub = item_subtotals[idx]
        # Resolve material name + color so the PDF can show the user-facing
        # version ("PLA · Branco" rather than just the polymer type).
        mat_name = mat_color = mat_manufacturer = None
        if it.material_version_id:
            mv = await session.get(MaterialVersion, it.material_version_id)
            if mv:
                mat_name = mv.name
                mat_color = mv.color
                mat_manufacturer = mv.manufacturer
        if items_cost > 0:
            client_price = (
                items_total_after_markup * sub / items_cost
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            client_price = Decimal("0")
        qty = int(it.quantity or 1)
        per_piece = (client_price / Decimal(qty)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        ) if qty else client_price
        item_dicts.append(
            {
                "name": it.name,
                "filament_m": it.gcode_meta.get("filament_m") or 0,
                "time_s": it.gcode_meta.get("time_s") or 0,
                "qty": qty,
                "subtotal": float(sub),
                "client_price": float(client_price),
                "client_price_per_piece": float(per_piece),
                "material_name": mat_name,
                "material_color": mat_color,
                "material_manufacturer": mat_manufacturer,
                "material_polymer": it.gcode_meta.get("material") or None,
                "is_multi_color": bool(it.is_multi_color),
                "model_source_url": it.model_source_url,
                "model_source_author": it.model_source_author,
                "model_source_license": it.model_source_license,
            }
        )
    total_pieces = sum(int(it.quantity or 1) for it in items)
    price_per_piece = (
        (total / Decimal(total_pieces)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if total_pieces > 0
        else Decimal("0")
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
        "retail_mode": bool(q.retail_mode),
        "quote": {
            "id": str(q.id)[:8],
            "kind": q.kind,
            "status": q.status,
            "client": client_name,
        },
        "items": item_dicts,
        "services": service_dicts,
        "total_pieces": int(total_pieces),
        "price_per_piece": float(price_per_piece),
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
