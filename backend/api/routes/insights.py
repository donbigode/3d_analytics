"""Insights overview — aggregates operational + LLM signals into a single
read-only payload for the /insights page. Distinct from /calibration which
only covers material auto-tuning.

The goal is to answer "what's the system seeing about your business this
month?" — operational pulse, recurring demand, material economics, LLM
activity, and a few attention flags.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import db_session, require_user
from backend.core.insights.personal_projects import compute_personal_projects
from backend.core.llm_features.runner import LLMUnavailable
from backend.core.models import QuoteKind, QuoteStatus
from backend.core.production.suggestions import generate_suggestions
from backend.infra.db.models import (
    Client,
    LLMDigest,
    MaterialVersion,
    ProductionEvent,
    ProductionSuggestion,
    Quote,
    QuoteItem,
    User,
)

router = APIRouter()


def _now() -> datetime:
    return datetime.now(timezone.utc)


@router.get("/personal-projects")
async def personal_projects(
    period_from: date | None = Query(None),
    period_to: date | None = Query(None),
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    pt = period_to or _now().date()
    pf = period_from or (pt - timedelta(days=365))
    return await compute_personal_projects(session, pf, pt)


@router.get("/failure-rates")
async def failure_rates(
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    """Taxa de falha agregada por material, a partir de production_events.

    Cada evento conta uma vez por material distinto presente no seu contexto
    (um orçamento pode misturar materiais). Puro SQL/Python, sem IA."""
    events = (await session.execute(select(ProductionEvent))).scalars().all()
    agg: dict[str, dict[str, int]] = {}
    for e in events:
        mats = {
            (piece or {}).get("material_type")
            for piece in (e.context or [])
            if (piece or {}).get("material_type")
        }
        for mt in (mats or {None}):
            key = mt or "—"
            bucket = agg.setdefault(key, {"failures": 0, "total": 0})
            bucket["total"] += 1
            if e.outcome == "failure":
                bucket["failures"] += 1
    by_material = [
        {
            "material_type": k,
            "failures": v["failures"],
            "total": v["total"],
            "failure_rate": (v["failures"] / v["total"]) if v["total"] else 0.0,
        }
        for k, v in sorted(agg.items())
    ]
    return {"by_material": by_material}


@router.get("/production-suggestions")
async def production_suggestions(
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    row = (
        await session.execute(
            select(ProductionSuggestion)
            .order_by(desc(ProductionSuggestion.generated_at))
            .limit(1)
        )
    ).scalars().first()
    total_fail = (
        await session.scalar(
            select(func.count(ProductionEvent.id)).where(
                ProductionEvent.outcome == "failure"
            )
        )
        or 0
    )
    if not row:
        return {
            "suggestions": [],
            "generated_at": None,
            "source_count": 0,
            "current_failures": total_fail,
            "stale": total_fail > 0,
        }
    body = row.body or {}
    return {
        "suggestions": body.get("suggestions", []),
        "generated_at": row.generated_at.isoformat(),
        "source_count": row.source_count,
        "current_failures": total_fail,
        "stale": total_fail != row.source_count,
    }


@router.post("/production-suggestions/generate")
async def production_suggestions_generate(
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    try:
        return await generate_suggestions(session)
    except LLMUnavailable as exc:
        raise HTTPException(503, f"IA indisponível: {exc}")


@router.get("/overview")
async def overview(
    days: int = 90,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    """Return a dictionary of aggregated insights for the past ``days``.

    Shape is intentionally flat-ish so the frontend can drop new sections
    without coordinating a schema change. Numbers are pre-rounded where
    relevant; the UI just formats them.
    """
    horizon = _now() - timedelta(days=days)
    short_horizon = _now() - timedelta(days=30)

    # ---- Commercial funnel (last 30d) -----------------------------------
    commercial_q = (
        await session.execute(
            select(Quote.status, func.count(Quote.id))
            .where(
                Quote.kind == QuoteKind.COMMERCIAL.value,
                Quote.created_at >= short_horizon,
            )
            .group_by(Quote.status)
        )
    ).all()
    funnel = {s: int(n) for s, n in commercial_q}

    finalized = sum(
        funnel.get(s, 0)
        for s in (
            QuoteStatus.ORCADO.value,
            QuoteStatus.APROVADO.value,
            QuoteStatus.PRODUZIDO.value,
            QuoteStatus.ENTREGUE.value,
        )
    )
    approved_plus = sum(
        funnel.get(s, 0)
        for s in (
            QuoteStatus.APROVADO.value,
            QuoteStatus.PRODUZIDO.value,
            QuoteStatus.ENTREGUE.value,
        )
    )
    conversion_pct = (
        round(100 * approved_plus / finalized, 1) if finalized > 0 else 0.0
    )

    # ---- Average ticket (last 30d, approved+) ---------------------------
    # We don't store ``total`` on Quote so we approximate by summing items
    # × (1+markup) per quote. For the dashboard's purposes this is good
    # enough — the user already sees exact numbers per quote.
    approved_quotes = (
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
                Quote.created_at >= short_horizon,
            )
        )
    ).scalars().all()
    avg_ticket: float | None = None
    if approved_quotes:
        # Sum subtotals × (1+markup/100); simple, ignores min_charge edge cases.
        total = Decimal("0")
        n = 0
        for q in approved_quotes:
            items = (
                await session.execute(
                    select(QuoteItem).where(QuoteItem.quote_id == q.id)
                )
            ).scalars().all()
            if not items:
                continue
            # Reuse the rough estimate the LLM markup feature uses.
            base = Decimal("0")
            for it in items:
                grams = Decimal(str(it.gcode_meta.get("filament_m") or 0)) * Decimal("2.4")  # rough mm³→g for PLA
                # No price lookup here to keep this fast — just count items.
                base += Decimal(int(it.quantity or 1))
            total += (Decimal("1") + q.markup_pct / Decimal("100")) * base
            n += 1
        if n > 0:
            avg_ticket = float((total / n).quantize(Decimal("0.01")))

    # ---- Top materials by total grams + by revenue (last N days) -------
    items_window = (
        await session.execute(
            select(QuoteItem, Quote)
            .join(Quote, Quote.id == QuoteItem.quote_id)
            .where(Quote.created_at >= horizon)
        )
    ).all()

    material_grams: dict[str, float] = {}
    material_revenue: dict[str, float] = {}
    name_counter: Counter = Counter()
    source_counter: Counter = Counter()
    multi_color_total = 0
    multi_color_count = 0

    # Cache material versions to avoid N+1.
    mv_cache: dict[str, MaterialVersion] = {}
    for it, q in items_window:
        name = (it.name or "").strip().lower()
        if name and len(name) >= 3:
            name_counter[name] += int(it.quantity or 1)

        url = (it.model_source_url or "").lower()
        if "printables.com" in url:
            src = "printables"
        elif "thingiverse.com" in url:
            src = "thingiverse"
        elif "makerworld.com" in url:
            src = "makerworld"
        elif "cults3d.com" in url:
            src = "cults3d"
        elif url:
            src = "outro"
        else:
            src = "interno"
        source_counter[src] += 1

        multi_color_total += 1
        if it.is_multi_color:
            multi_color_count += 1

        if not it.material_version_id:
            continue
        mid = str(it.material_version_id)
        mv = mv_cache.get(mid)
        if mv is None:
            mv = await session.get(MaterialVersion, it.material_version_id)
            mv_cache[mid] = mv
        if mv is None:
            continue

        # grams used (rough): filament_m × π × (1.75/2)² × density
        meters = float(it.gcode_meta.get("filament_m") or 0)
        # 2.4053 mm³/mm linear at 1.75mm
        grams_per_m = 2.4053 * float(mv.density_g_cm3)
        grams = meters * grams_per_m * int(it.quantity or 1)
        if grams > 0:
            key = f"{mv.name} · {mv.color or '—'}"
            material_grams[key] = material_grams.get(key, 0.0) + grams
            # Revenue contribution (approx): grams × price_per_kg / 1000.
            material_revenue[key] = (
                material_revenue.get(key, 0.0)
                + grams * float(mv.price_per_kg_ref) / 1000.0
            )

    top_materials_grams = sorted(
        material_grams.items(), key=lambda kv: kv[1], reverse=True
    )[:5]
    top_materials_revenue = sorted(
        material_revenue.items(), key=lambda kv: kv[1], reverse=True
    )[:5]
    top_names = name_counter.most_common(5)

    # ---- LLM digest peek ------------------------------------------------
    latest_digest = (
        await session.execute(
            select(LLMDigest).order_by(LLMDigest.digest_date.desc()).limit(1)
        )
    ).scalar_one_or_none()
    digest_payload = None
    if latest_digest:
        digest_payload = {
            "date": latest_digest.digest_date.isoformat(),
            "provider": latest_digest.provider,
            "body": latest_digest.body,
        }
    digest_count = await session.scalar(
        select(func.count(LLMDigest.id)).where(LLMDigest.created_at >= horizon)
    )

    # ---- Attention flags -----------------------------------------------
    pending_items = await session.scalar(
        select(func.count(QuoteItem.id))
        .join(Quote, Quote.id == QuoteItem.quote_id)
        .where(
            QuoteItem.material_version_id.is_(None),
            Quote.status == QuoteStatus.DRAFT.value,
        )
    )
    stalled_threshold = _now() - timedelta(days=7)
    stalled = await session.scalar(
        select(func.count(Quote.id)).where(
            Quote.kind == QuoteKind.COMMERCIAL.value,
            Quote.status == QuoteStatus.ORCADO.value,
            Quote.finalized_at < stalled_threshold,
        )
    )

    # ---- Repeat clients (last horizon) ---------------------------------
    repeat_clients_rows = (
        await session.execute(
            select(Client.name, func.count(Quote.id).label("n"))
            .join(Quote, Quote.client_id == Client.id)
            .where(Quote.created_at >= horizon)
            .group_by(Client.name)
            .order_by(func.count(Quote.id).desc())
            .limit(5)
        )
    ).all()
    top_clients = [(name, int(n)) for name, n in repeat_clients_rows]

    return {
        "window_days": days,
        "funnel": funnel,
        "conversion_pct": conversion_pct,
        "approved_count": approved_plus,
        "finalized_count": finalized,
        "avg_ticket": avg_ticket,
        "top_materials_grams": [
            {"label": k, "grams": round(v, 1)} for k, v in top_materials_grams
        ],
        "top_materials_revenue": [
            {"label": k, "revenue": round(v, 2)} for k, v in top_materials_revenue
        ],
        "top_names": [{"name": n, "count": c} for n, c in top_names],
        "source_attribution": [
            {"site": s, "count": c} for s, c in source_counter.most_common()
        ],
        "multi_color_share_pct": (
            round(100 * multi_color_count / multi_color_total, 1)
            if multi_color_total > 0
            else 0.0
        ),
        "latest_digest": digest_payload,
        "digest_count_window": int(digest_count or 0),
        "alerts": {
            "pending_items_draft": int(pending_items or 0),
            "stalled_quotes": int(stalled or 0),
        },
        "top_clients": [{"name": n, "count": c} for n, c in top_clients],
    }
