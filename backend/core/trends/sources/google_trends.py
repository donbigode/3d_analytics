"""Google Trends adapter using pytrends (sync) bridged to asyncio.

Returns the mean interest_over_time for Brazil scaled 0..100. The lookback
window is configurable per call:

  - day   → ``now 1-d``   (last 24h)
  - week  → ``now 7-d``   (last 7 days)
  - month → ``today 1-m`` (last 30 days, default)

Returns None on any transient failure (rate limit, empty payload, network
error) — the scheduler logs and continues.
"""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)

_TIMEFRAMES = {
    "day": "now 1-d",
    "week": "now 7-d",
    "month": "today 1-m",
}


def _fetch_sync(term: str, *, window: str = "month") -> Decimal | None:
    timeframe = _TIMEFRAMES.get(window, _TIMEFRAMES["month"])

    try:
        from pytrends.request import TrendReq  # local import: optional dep
    except Exception as exc:  # pragma: no cover - import-time guard
        logger.warning("pytrends import failed: %s", exc)
        return None

    try:
        pytrends = TrendReq(hl="pt-BR", tz=180)
        pytrends.build_payload([term], timeframe=timeframe, geo="BR")
        df = pytrends.interest_over_time()
        if df is None or df.empty or term not in df.columns:
            return None
        series = df[term].dropna()
        if series.empty:
            return None
        mean = float(series.mean())
        return Decimal(str(round(mean, 2)))
    except Exception as exc:
        logger.warning(
            "google_trends fetch failed for %r (window=%s): %s", term, window, exc
        )
        return None


async def fetch_interest(term: str, *, window: str = "month") -> Decimal | None:
    """Async wrapper. ``window`` is one of 'day' | 'week' | 'month'."""
    return await asyncio.to_thread(_fetch_sync, term, window=window)
