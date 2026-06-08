"""YouTube Data API v3 adapter — free tier (10k units/day, plenty for us).

Two calls per term:
  1. search.list?q=<term>&type=video&order=relevance&maxResults=10  (100 units)
  2. videos.list?id=<csv-of-ids>&part=statistics                    (1 unit/id)

Together that's ~110 units per term. With 10k/day quota and ~10 terms cadastrados
the daily collect uses ~1100 units — well under the limit.

The signal we publish is the sum of viewCount across the top 10 video results,
which is a robust proxy for content saturation around the keyword: low view
totals = niche/empty (room to grow); high view totals = saturated.

Returns ``{}`` if no API key is set or any HTTP/parse failure occurs.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

import httpx

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
_TIMEOUT = httpx.Timeout(15.0)


async def fetch_views(
    term: str,
    *,
    api_key: str | None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Return ``{views_total, videos_count, top_videos}`` or empty dict."""
    if not api_key:
        return {}

    own = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=_TIMEOUT)

    try:
        try:
            r = await client.get(
                SEARCH_URL,
                params={
                    "part": "id,snippet",
                    "q": term,
                    "type": "video",
                    "order": "relevance",
                    "maxResults": 10,
                    "regionCode": "BR",
                    "relevanceLanguage": "pt",
                    "key": api_key,
                },
            )
            r.raise_for_status()
            search = r.json()
        except Exception as exc:
            logger.warning("youtube search failed for %r: %s", term, exc)
            return {}

        items = search.get("items") or []
        if not items:
            return {"views_total": Decimal("0"), "videos_count": 0, "top_videos": []}

        ids = [
            it.get("id", {}).get("videoId")
            for it in items
            if isinstance(it.get("id"), dict)
        ]
        ids = [vid for vid in ids if vid]
        if not ids:
            return {"views_total": Decimal("0"), "videos_count": 0, "top_videos": []}

        try:
            r2 = await client.get(
                VIDEOS_URL,
                params={
                    "part": "statistics,snippet",
                    "id": ",".join(ids),
                    "key": api_key,
                },
            )
            r2.raise_for_status()
            videos = r2.json()
        except Exception as exc:
            logger.warning("youtube videos.list failed for %r: %s", term, exc)
            return {}

        v_items = videos.get("items") or []
        views_total = Decimal("0")
        top_videos: list[dict[str, Any]] = []
        for v in v_items:
            stats = v.get("statistics") or {}
            snippet = v.get("snippet") or {}
            try:
                vc = int(stats.get("viewCount") or 0)
            except (TypeError, ValueError):
                vc = 0
            views_total += Decimal(vc)
            if len(top_videos) < 5:
                vid = v.get("id") or ""
                top_videos.append(
                    {
                        "title": snippet.get("title") or "",
                        "channel": snippet.get("channelTitle") or "",
                        "views": vc,
                        "url": f"https://www.youtube.com/watch?v={vid}" if vid else None,
                    }
                )

        return {
            "views_total": views_total,
            "videos_count": len(v_items),
            "top_videos": top_videos,
        }
    finally:
        if own:
            await client.aclose()
