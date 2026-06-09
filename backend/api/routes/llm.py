"""LLM feature endpoints — daily digest, auto-name, markup, variance, pricing, variants."""
from __future__ import annotations

import math
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import db_session, require_user
from backend.api.schemas.llm import (
    AutoNameOut,
    DigestOut,
    MarkupSuggestionOut,
    PricingOut,
    VarianceOut,
    VariantSuggestion,
    VariantsOut,
)
from backend.core.llm_features import LLMUnavailable
from backend.core.llm_features.auto_name import suggest_name
from backend.core.llm_features.digest import generate_digest
from backend.core.llm_features.markup import suggest_markup
from backend.core.llm_features.pricing import suggest_price
from backend.core.llm_features.variance import explain_variance
from backend.core.llm_features.variants import suggest_variants
from backend.core.pricing.cost import (
    depreciation_cost,
    energy_cost,
    filament_cost,
    grams_from_meters,
)
from backend.infra.db.models import (
    LLMDigest,
    MaterialConsumption,
    MaterialVersion,
    Quote,
    QuoteItem,
    QuoteService,
    Settings,
    User,
    WatcherInboxFile,
)

router = APIRouter()


# ---------- Digest ----------

@router.get("/digest", response_model=DigestOut)
async def get_digest(
    force: bool = Query(False),
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    today = date.today()
    if not force:
        existing = (
            await session.execute(
                select(LLMDigest).where(LLMDigest.digest_date == today)
            )
        ).scalar_one_or_none()
        if existing:
            return DigestOut(
                date=today,
                provider=existing.provider,
                body=existing.body,
                cached=True,
                created_at=existing.created_at,
            )

    try:
        body, provider = await generate_digest(session)
    except LLMUnavailable as exc:
        raise HTTPException(503, f"LLM indisponível: {exc}")

    # Upsert today's row
    existing = (
        await session.execute(select(LLMDigest).where(LLMDigest.digest_date == today))
    ).scalar_one_or_none()
    if existing:
        existing.body = body
        existing.provider = provider
        await session.commit()
        await session.refresh(existing)
        row = existing
    else:
        row = LLMDigest(digest_date=today, provider=provider, body=body)
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return DigestOut(
        date=today, provider=provider, body=body, cached=False, created_at=row.created_at
    )


# ---------- Auto-name ----------

@router.post("/auto-name/{inbox_id}", response_model=AutoNameOut)
async def auto_name(
    inbox_id: UUID,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    item = await session.get(WatcherInboxFile, inbox_id)
    if not item:
        raise HTTPException(404)
    try:
        data = await suggest_name(session, item)
    except LLMUnavailable as exc:
        raise HTTPException(503, str(exc))
    return AutoNameOut(
        inbox_id=str(inbox_id),
        name=data.get("name") or "—",
        confidence=data.get("confidence"),
        why=data.get("why"),
    )


# ---------- Markup ----------

@router.post("/markup/{quote_id}", response_model=MarkupSuggestionOut)
async def markup(
    quote_id: UUID,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    q = await session.get(Quote, quote_id)
    if not q:
        raise HTTPException(404)
    try:
        data = await suggest_markup(session, q)
    except LLMUnavailable as exc:
        raise HTTPException(503, str(exc))
    raw_market = data.get("market_price_ref")
    try:
        market_ref = Decimal(str(raw_market)) if raw_market not in (None, "", "null") else None
    except Exception:  # noqa: BLE001
        market_ref = None
    return MarkupSuggestionOut(
        quote_id=str(quote_id),
        suggested_markup_pct=Decimal(str(data.get("suggested_markup_pct") or q.markup_pct)),
        complexity=data.get("complexity"),
        rationale=data.get("rationale"),
        market_price_ref=market_ref,
    )


# ---------- Variance ----------

_DIAM = Decimal("1.75")
_PI4 = Decimal("3.14159265358979323846") / Decimal(4)


async def _compute_orcado_real(
    session: AsyncSession, quote: Quote
) -> tuple[Decimal, Decimal]:
    """Replicate the same numbers G6 shows on the dashboard."""
    settings_row = await session.get(Settings, 1) or Settings(id=1)
    items = (
        await session.execute(select(QuoteItem).where(QuoteItem.quote_id == quote.id))
    ).scalars().all()
    services = (
        await session.execute(select(QuoteService).where(QuoteService.quote_id == quote.id))
    ).scalars().all()

    item_grams_cost = Decimal(0)
    item_energy = Decimal(0)
    item_dep = Decimal(0)
    real_filament = Decimal(0)

    for it in items:
        if not it.material_version_id:
            continue
        mv = await session.get(MaterialVersion, it.material_version_id)
        if not mv:
            continue
        filament_m = float(it.gcode_meta.get("filament_m") or 0)
        time_s = float(it.gcode_meta.get("time_s") or 0)
        grams = grams_from_meters(filament_m, mv.density_g_cm3, _DIAM) * Decimal(it.quantity)
        item_grams_cost += filament_cost(grams, mv.price_per_kg_ref)
        item_energy += energy_cost(time_s, settings_row.printer_power_w, settings_row.energy_kwh_price)
        dep_rate = it.depreciation_rate_override or settings_row.printer_depreciation_per_hour
        item_dep += depreciation_cost(time_s, dep_rate)
        cons = (
            await session.execute(
                select(MaterialConsumption).where(
                    MaterialConsumption.quote_item_id == it.id
                )
            )
        ).scalars().all()
        for c in cons:
            real_filament += c.grams_used * c.unit_cost_snapshot

    services_cost = sum((s.quantity * s.rate for s in services), Decimal(0))
    orcado = item_grams_cost + item_energy + item_dep + services_cost
    real = real_filament + item_energy + item_dep + services_cost
    return orcado, real


@router.post("/variance/{quote_id}", response_model=VarianceOut)
async def variance(
    quote_id: UUID,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    q = await session.get(Quote, quote_id)
    if not q:
        raise HTTPException(404)
    orcado, real = await _compute_orcado_real(session, q)
    if orcado <= 0:
        raise HTTPException(409, "quote has no cost to compare")
    try:
        explanation = await explain_variance(session, q, orcado=orcado, real=real)
    except LLMUnavailable as exc:
        raise HTTPException(503, str(exc))
    pct = (real - orcado) / orcado * Decimal(100)
    return VarianceOut(
        quote_id=str(quote_id),
        orcado=orcado.quantize(Decimal("0.01")),
        real=real.quantize(Decimal("0.01")),
        variance_pct=pct.quantize(Decimal("0.01")),
        explanation=explanation,
    )


# ---------- Pricing ----------

@router.post("/pricing/{quote_id}", response_model=PricingOut)
async def pricing(
    quote_id: UUID,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    q = await session.get(Quote, quote_id)
    if not q:
        raise HTTPException(404)
    orcado, _ = await _compute_orcado_real(session, q)
    try:
        data = await suggest_price(session, q, orcado_cost=orcado)
    except LLMUnavailable as exc:
        raise HTTPException(503, str(exc))
    return PricingOut(
        quote_id=str(quote_id),
        cost=orcado.quantize(Decimal("0.01")),
        suggested_price=Decimal(str(data.get("suggested_price") or 0)),
        floor=Decimal(str(data.get("floor") or 0)),
        ceiling=Decimal(str(data.get("ceiling") or 0)),
        rationale=data.get("rationale"),
    )


# ---------- Variants ----------

@router.post("/variants/items/{item_id}", response_model=VariantsOut)
async def variants(
    item_id: UUID,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    item = await session.get(QuoteItem, item_id)
    if not item:
        raise HTTPException(404)
    try:
        data = await suggest_variants(session, item)
    except LLMUnavailable as exc:
        raise HTTPException(503, str(exc))
    out_variants = []
    for v in (data.get("variants") or [])[:8]:
        if not isinstance(v, dict):
            continue
        out_variants.append(
            VariantSuggestion(
                name=str(v.get("name") or "—"),
                material=v.get("material"),
                angle=v.get("angle"),
            )
        )
    return VariantsOut(item_id=str(item_id), variants=out_variants)
