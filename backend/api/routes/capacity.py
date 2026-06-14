"""Capacity / schedule forecast endpoints (Wave 5 Lane F2).

Pure read-only computation on the approved-quote queue. No writes, no DB
changes. The heavy lifting lives in `backend.core.capacity.forecast` so it can
be unit-tested without a DB.
"""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import db_session, require_user
from backend.api.schemas.capacity import ForecastOut, InProductionOut, QuoteEtaOut
from backend.core.capacity import QuoteSummary, compute_forecast
from backend.core.models import QuoteKind, QuoteStatus
from backend.infra.db.models import Quote, QuoteItem, Settings, User

router = APIRouter()


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _hours_per_day(session: AsyncSession) -> Decimal:
    s = await session.get(Settings, 1)
    if s is None:
        return Decimal("22")
    return Decimal(s.printer_hours_per_day or 22)


def _quote_hours(items: list[QuoteItem]) -> Decimal:
    total_s = Decimal("0")
    for it in items:
        time_s = (it.gcode_meta or {}).get("time_s") or 0
        try:
            t = Decimal(str(time_s))
        except Exception:
            t = Decimal("0")
        total_s += t * Decimal(it.quantity or 0)
    return total_s / Decimal("3600")


async def _build_queue(session: AsyncSession) -> list[QuoteSummary]:
    """FIFO queue of approved commercial quotes (oldest approved first)."""
    res = await session.execute(
        select(Quote)
        .where(
            Quote.kind == QuoteKind.COMMERCIAL,
            Quote.status == QuoteStatus.APROVADO,
        )
        .order_by(Quote.approved_at.asc().nulls_last(), Quote.created_at.asc())
    )
    quotes = list(res.scalars())
    queue: list[QuoteSummary] = []
    for q in quotes:
        items_res = await session.execute(
            select(QuoteItem).where(QuoteItem.quote_id == q.id)
        )
        items = list(items_res.scalars())
        hours = _quote_hours(items)
        # First item's name is a reasonable short label; fall back to short id.
        label = items[0].name if items else str(q.id)[:8]
        queue.append(
            QuoteSummary(
                quote_id=str(q.id),
                name=label,
                hours=hours,
            )
        )
    return queue


@router.get("/forecast", response_model=ForecastOut)
async def get_forecast(
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    hpd = await _hours_per_day(session)
    queue = await _build_queue(session)
    f = compute_forecast(queue=queue, hours_per_day=hpd, now=_now())
    return ForecastOut(
        hours_per_day=f.hours_per_day,
        queue_hours=f.queue_hours,
        queue_jobs=f.queue_jobs,
        days_until_clear=f.days_until_clear,
        next_available_at=f.next_available_at,
        jobs=[
            {
                "quote_id": j.quote_id,
                "name": j.name,
                "hours": j.hours,
                "eta": j.eta,
            }
            for j in f.jobs
        ],
    )


@router.get("/in-production", response_model=InProductionOut)
async def in_production(
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    """FIFO of jobs currently on the printer (status em_producao), oldest first.

    Distinct from /forecast (which forecasts the aprovado backlog). This is the
    live queue where Capacidade marks Concluir/Falhar."""
    res = await session.execute(
        select(Quote)
        .where(Quote.status == QuoteStatus.EM_PRODUCAO)
        .order_by(Quote.produced_at.asc().nulls_last(), Quote.created_at.asc())
    )
    jobs = []
    for q in res.scalars():
        items = list(
            (
                await session.execute(
                    select(QuoteItem).where(QuoteItem.quote_id == q.id)
                )
            ).scalars()
        )
        jobs.append(
            {
                "quote_id": str(q.id),
                "name": (items[0].name if items else str(q.id)[:8]),
                "kind": q.kind,
                "hours": _quote_hours(items),
                "entered_at": q.produced_at,
            }
        )
    return InProductionOut(jobs=jobs)


@router.get("/forecast/quotes/{quote_id}", response_model=QuoteEtaOut)
async def get_quote_eta(
    quote_id: UUID,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    q = await session.get(Quote, quote_id)
    if not q:
        raise HTTPException(404, "quote not found")

    hpd = await _hours_per_day(session)
    queue = await _build_queue(session)
    f = compute_forecast(queue=queue, hours_per_day=hpd, now=_now())

    target = str(quote_id)
    for idx, job in enumerate(f.jobs):
        if job.quote_id == target:
            return QuoteEtaOut(
                quote_id=target,
                in_queue=True,
                position=idx + 1,
                hours=job.hours,
                eta=job.eta,
                next_available_at=f.next_available_at,
            )

    # Quote exists but is not in the approved queue: report its own hours and
    # the next-available window as a best-effort ETA proxy.
    items_res = await session.execute(
        select(QuoteItem).where(QuoteItem.quote_id == q.id)
    )
    own_hours = _quote_hours(list(items_res.scalars()))
    return QuoteEtaOut(
        quote_id=target,
        in_queue=False,
        position=None,
        hours=own_hours.quantize(Decimal("0.01")),
        eta=None,
        next_available_at=f.next_available_at,
    )
