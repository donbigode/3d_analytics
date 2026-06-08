"""Google Trends adapter using pytrends (sync) bridged to asyncio.

Returns the mean interest_over_time for Brazil scaled 0..100. The lookback
window is configurable per call:

  - day   → ``now 1-d``   (last 24h)
  - week  → ``now 7-d``   (last 7 days)
  - month → ``today 1-m`` (last 30 days, default)

Returns None on empty series. Raises :class:`GoogleTrendsRateLimited` on
429 — the scheduler catches it once and stops hammering Google for the rest
of the collect pass.

For other transient failures (network, parse) returns None and lets the
scheduler log a soft miss.
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


class GoogleTrendsRateLimited(Exception):
    """Raised when pytrends signals an HTTP 429.

    Google's rate limit is aggressive and IP-bound — once we see it, we know
    every other term in this batch will hit the same wall, so the scheduler
    should bail out instead of burning a request per term.
    """


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
        msg = str(exc)
        if "429" in msg or "rate" in msg.lower():
            raise GoogleTrendsRateLimited(msg) from exc
        logger.warning(
            "google_trends fetch failed for %r (window=%s): %s", term, window, exc
        )
        return None


async def fetch_interest(term: str, *, window: str = "month") -> Decimal | None:
    """Async wrapper. ``window`` is one of 'day' | 'week' | 'month'.

    Raises :class:`GoogleTrendsRateLimited` on 429 — caller should bail out
    of the batch.
    """
    return await asyncio.to_thread(_fetch_sync, term, window=window)
