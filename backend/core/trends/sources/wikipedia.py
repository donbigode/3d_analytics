"""Wikipedia pageviews adapter — completely free, no auth required.

The Wikimedia REST API serves daily pageviews per article going back to
2015-07-01. We hit the PT-BR project (``pt.wikipedia``), aggregate the last
N days for a given term (best-effort title match), and return the mean
daily views as an "interest" metric on a similar scale to Google Trends
(though absolute, not normalised).

Docs: https://wikitech.wikimedia.org/wiki/Analytics/AQS/Pageviews

The function returns ``None`` on any HTTP/parse failure — the scheduler logs
and continues. Articles in titles map approximately: we URL-encode the term
and let Wikipedia handle redirects via the article-info endpoint.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

PROJECT = "pt.wikipedia"
USER_AGENT = "3d-analytics/0.1 (operator@local; trend radar)"
_TIMEOUT = httpx.Timeout(15.0)

_WINDOWS_DAYS = {"day": 1, "week": 7, "month": 30}


def _date_range(window: str) -> tuple[str, str]:
    days = _WINDOWS_DAYS.get(window, 30)
    today = date.today()
    # The Pageviews API takes inclusive YYYYMMDD with no separators. End date
    # must be at least one day in the past (counts settle daily).
    end = today - timedelta(days=1)
    start = end - timedelta(days=days - 1)
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def _normalize_title(term: str) -> str:
    """Wikipedia titles use ``_`` for spaces and are case-sensitive on first letter."""
    cleaned = term.strip().replace(" ", "_")
    if cleaned and cleaned[0].islower():
        cleaned = cleaned[0].upper() + cleaned[1:]
    return cleaned


async def fetch_interest(
    term: str,
    *,
    window: str = "month",
    client: httpx.AsyncClient | None = None,
) -> Decimal | None:
    """Mean daily pageviews on PT Wikipedia over the requested window.

    Returns None on any failure (article not found, transient HTTP error, etc).
    """
    title = _normalize_title(term)
    if not title:
        return None
    start, end = _date_range(window)
    url = (
        f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
        f"{PROJECT}/all-access/all-agents/{quote(title)}/daily/{start}/{end}"
    )

    own = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=_TIMEOUT, headers={"User-Agent": USER_AGENT})
    try:
        try:
            r = await client.get(url)
            r.raise_for_status()
            data = r.json()
        except Exception as exc:
            logger.info("wikipedia fetch failed for %r (%s): %s", term, window, exc)
            return None
        items = data.get("items") or []
        if not items:
            return None
        total = sum(int(it.get("views") or 0) for it in items)
        avg = Decimal(total) / Decimal(len(items))
        return avg.quantize(Decimal("0.01"))
    finally:
        if own:
            await client.aclose()
