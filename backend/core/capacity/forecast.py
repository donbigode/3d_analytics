"""Pure forecast computation for the print queue.

Given a FIFO list of approved jobs (each with total print hours) and a daily
capacity (hours/day), compute:

  - total queue hours / job count
  - days until the queue is clear (ceil of queue_hours / hours_per_day)
  - the next-available datetime (when the queue empties)
  - per-job ETAs (also a datetime — when each job will be produced)

MVP simplifications (documented behavior):
  - Days are continuous; no weekends/holidays excluded.
  - The current calendar day is treated as fully available — we do not subtract
    "hours already elapsed today". This errs on the optimistic side but is
    consistent with how a small workshop usually thinks of it.
  - Personal in-progress jobs are out of scope here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal


@dataclass(frozen=True)
class QuoteSummary:
    """Minimal projection of a queued approved quote.

    `hours` is the total print time for the quote (sum of time_s × quantity
    across items, converted to hours). `approved_at` is used only for stable
    FIFO ordering by the caller; the forecast function assumes the list is
    already in the desired order.
    """
    quote_id: str
    name: str
    hours: Decimal


@dataclass(frozen=True)
class ForecastJob:
    quote_id: str
    name: str
    hours: Decimal
    eta: datetime


@dataclass(frozen=True)
class Forecast:
    hours_per_day: Decimal
    queue_hours: Decimal
    queue_jobs: int
    days_until_clear: int
    next_available_at: datetime
    jobs: list[ForecastJob] = field(default_factory=list)


def _quantize_hours(h: Decimal) -> Decimal:
    return Decimal(h).quantize(Decimal("0.01"))


def compute_forecast(
    queue: list[QuoteSummary],
    hours_per_day: Decimal,
    now: datetime,
) -> Forecast:
    """Compute the schedule forecast for a FIFO queue.

    The caller is responsible for ordering `queue` (typically by `approved_at`
    ASC). `hours_per_day` must be > 0 — we clamp 0 / negative to 1 to avoid
    divide-by-zero and degenerate timelines.
    """
    hpd = Decimal(hours_per_day)
    if hpd <= 0:
        hpd = Decimal("1")

    total_hours = sum((Decimal(q.hours) for q in queue), Decimal("0"))

    # Each job's ETA is `now + cumulative_hours / hpd` days.
    jobs: list[ForecastJob] = []
    cumulative = Decimal("0")
    for q in queue:
        cumulative += Decimal(q.hours)
        days = float(cumulative / hpd)
        eta = now + timedelta(days=days)
        jobs.append(
            ForecastJob(
                quote_id=q.quote_id,
                name=q.name,
                hours=_quantize_hours(q.hours),
                eta=eta,
            )
        )

    # days_until_clear is the ceiling so we never under-promise the window.
    if total_hours <= 0:
        days_until_clear = 0
    else:
        # Use Decimal-safe ceil: -(-a // b) gives floor when both are positive,
        # so we compute floor and add one if there's any remainder.
        q, r = divmod(total_hours, hpd)
        days_until_clear = int(q) + (1 if r > 0 else 0)

    next_available = now + timedelta(days=float(total_hours / hpd))

    return Forecast(
        hours_per_day=hpd,
        queue_hours=_quantize_hours(total_hours),
        queue_jobs=len(queue),
        days_until_clear=days_until_clear,
        next_available_at=next_available,
        jobs=jobs,
    )
