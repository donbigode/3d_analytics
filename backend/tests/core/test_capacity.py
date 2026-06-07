from datetime import datetime, timezone, timedelta
from decimal import Decimal

from backend.core.capacity import QuoteSummary, compute_forecast


NOW = datetime(2026, 6, 7, 12, 0, 0, tzinfo=timezone.utc)


def test_empty_queue_clears_immediately():
    f = compute_forecast(queue=[], hours_per_day=Decimal("22"), now=NOW)
    assert f.queue_hours == Decimal("0.00")
    assert f.queue_jobs == 0
    assert f.days_until_clear == 0
    assert f.next_available_at == NOW
    assert f.jobs == []


def test_single_short_job_fits_in_one_day():
    queue = [QuoteSummary(quote_id="q1", name="Bracket", hours=Decimal("5"))]
    f = compute_forecast(queue=queue, hours_per_day=Decimal("22"), now=NOW)
    assert f.queue_hours == Decimal("5.00")
    assert f.queue_jobs == 1
    assert f.days_until_clear == 1  # ceil(5/22) = 1
    # ETA is now + 5/22 of a day
    expected = NOW + timedelta(days=float(Decimal("5") / Decimal("22")))
    assert f.jobs[0].eta == expected
    assert f.next_available_at == expected
    assert f.jobs[0].quote_id == "q1"
    assert f.jobs[0].hours == Decimal("5.00")


def test_multi_day_spillover_fifo_etas_are_cumulative():
    # 3 jobs of 20h with 22h/day capacity: queue total = 60h ~= 2.73 days → ceil 3.
    queue = [
        QuoteSummary(quote_id="q1", name="A", hours=Decimal("20")),
        QuoteSummary(quote_id="q2", name="B", hours=Decimal("20")),
        QuoteSummary(quote_id="q3", name="C", hours=Decimal("20")),
    ]
    f = compute_forecast(queue=queue, hours_per_day=Decimal("22"), now=NOW)
    assert f.queue_hours == Decimal("60.00")
    assert f.queue_jobs == 3
    assert f.days_until_clear == 3

    # Each ETA increases monotonically, latest equals next_available.
    etas = [j.eta for j in f.jobs]
    assert etas[0] < etas[1] < etas[2]
    assert f.next_available_at == etas[-1]

    # 2nd job's ETA = now + 40/22 days
    expected_2nd = NOW + timedelta(days=float(Decimal("40") / Decimal("22")))
    assert etas[1] == expected_2nd


def test_eta_per_quote_is_position_in_fifo():
    # Confirm ETA of a specific quote_id matches its FIFO position.
    queue = [
        QuoteSummary(quote_id="alpha", name="A", hours=Decimal("10")),
        QuoteSummary(quote_id="beta", name="B", hours=Decimal("6")),
        QuoteSummary(quote_id="gamma", name="C", hours=Decimal("4")),
    ]
    f = compute_forecast(queue=queue, hours_per_day=Decimal("8"), now=NOW)
    by_id = {j.quote_id: j for j in f.jobs}
    # Beta finishes after 10+6=16h on a 8h/day -> +2 days
    assert by_id["beta"].eta == NOW + timedelta(days=2.0)
    # Gamma finishes after 20h -> 2.5 days
    assert by_id["gamma"].eta == NOW + timedelta(days=2.5)
    assert f.next_available_at == by_id["gamma"].eta
    assert f.days_until_clear == 3  # ceil(20/8) = 3


def test_zero_hours_per_day_is_clamped_to_one():
    # Defensive: zero or negative HPD should not divide-by-zero.
    queue = [QuoteSummary(quote_id="q1", name="x", hours=Decimal("3"))]
    f = compute_forecast(queue=queue, hours_per_day=Decimal("0"), now=NOW)
    assert f.hours_per_day == Decimal("1")
    assert f.days_until_clear == 3
