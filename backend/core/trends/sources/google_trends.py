"""Google Trends adapter using pytrends (sync) bridged to asyncio.

Returns the mean of the last 30 days of interest_over_time for Brazil, on a
0..100 scale. Returns None on any transient failure (rate limit, empty payload,
network error) — scheduler logs and continues.
"""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)


def _fetch_sync(term: str) -> Decimal | None:
    try:
        from pytrends.request import TrendReq  # local import: optional dep
    except Exception as exc:  # pragma: no cover - import-time guard
        logger.warning("pytrends import failed: %s", exc)
        return None

    try:
        pytrends = TrendReq(hl="pt-BR", tz=180)
        pytrends.build_payload([term], timeframe="today 1-m", geo="BR")
        df = pytrends.interest_over_time()
        if df is None or df.empty or term not in df.columns:
            return None
        series = df[term].dropna()
        if series.empty:
            return None
        mean = float(series.mean())
        return Decimal(str(round(mean, 2)))
    except Exception as exc:
        logger.warning("google_trends fetch failed for %r: %s", term, exc)
        return None


async def fetch_interest(term: str) -> Decimal | None:
    """Async wrapper around pytrends — mean of last 30 days, BR, 0..100."""
    return await asyncio.to_thread(_fetch_sync, term)
