"""Geração de PDF do orçamento.

Movido sem alteração de lógica a partir do antigo `backend/api/routes/quotes.py`.
"""
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import db_session, require_user
from backend.api.routes.quotes._shared import _build_item_input, _get_settings_row, _now
from backend.core.pricing.quote import (
    ItemInput,
    ServiceLine,
    compute_item_cost,
    compute_quote_total,
)
from backend.infra.db.models import Client, MaterialVersion, Quote, QuotePhoto, Service, User
from backend.infra.db.repos import quote as quote_repo
from backend.infra.pdf.render import render_quote_pdf
from backend.infra.storage import quote_photos as photo_storage
from backend.settings import get_settings as get_app_settings

router = APIRouter()


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

    all_photos = (await session.execute(
        select(QuotePhoto)
        .where(QuotePhoto.quote_id == q.id)
        .order_by(QuotePhoto.sort_order, QuotePhoto.created_at)
    )).scalars().all()
    cover_photo_uris = [
        photo_storage.absolute_uri(p.storage_path)
        for p in all_photos if p.quote_item_id is None
    ]
    item_photo_uris: dict[str, list[str]] = {}
    for p in all_photos:
        if p.quote_item_id is not None:
            item_photo_uris.setdefault(str(p.quote_item_id), []).append(
                photo_storage.absolute_uri(p.storage_path)
            )

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
                "photos": item_photo_uris.get(str(it.id), []),
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
            "seq": q.seq,
            "kind": q.kind,
            "status": q.status,
            "client": client_name,
        },
        "cover_photos": cover_photo_uris,
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
