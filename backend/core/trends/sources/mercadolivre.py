"""Mercado Livre search adapter — no auth required.

Returns aggregated stats over the top-20 results for the given term:
  - sold_quantity: sum of `sold_quantity` across results
  - avg_price:     mean of `price` across results
  - top_listings:  the first 5 results with title/price/sold (UI display)
  - sample_size:   how many results were aggregated

Defensive: returns an empty dict on any HTTP/parse failure.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

import httpx

logger = logging.getLogger(__name__)

ML_SEARCH_URL = "https://api.mercadolibre.com/sites/MLB/search"
_TIMEOUT = httpx.Timeout(10.0)


async def fetch_volume(term: str, *, client: httpx.AsyncClient | None = None) -> dict[str, Any]:
    """Hit ML public search and aggregate top-20 results.

    If `client` is provided it's used as-is (handy for tests with MockTransport).
    Otherwise opens a short-lived AsyncClient.
    """

    own_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=_TIMEOUT)

    try:
        try:
            r = await client.get(ML_SEARCH_URL, params={"q": term, "limit": 20})
            r.raise_for_status()
            data = r.json()
        except Exception as exc:
            logger.warning("mercadolivre fetch failed for %r: %s", term, exc)
            return {}

        results = data.get("results") or []
        if not results:
            return {
                "sold_quantity": Decimal("0"),
                "avg_price": Decimal("0"),
                "top_listings": [],
                "sample_size": 0,
            }

        prices: list[Decimal] = []
        sold_sum = Decimal("0")
        top_listings: list[dict[str, Any]] = []
        for item in results:
            try:
                price = item.get("price")
                sold = item.get("sold_quantity") or 0
                if price is not None:
                    prices.append(Decimal(str(price)))
                sold_sum += Decimal(str(sold))
                if len(top_listings) < 5:
                    top_listings.append(
                        {
                            "title": item.get("title") or "",
                            "price": float(price) if price is not None else None,
                            "sold": int(sold),
                            "permalink": item.get("permalink"),
                        }
                    )
            except Exception:
                continue

        avg_price = (
            (sum(prices) / Decimal(len(prices))).quantize(Decimal("0.01"))
            if prices
            else Decimal("0")
        )
        return {
            "sold_quantity": sold_sum,
            "avg_price": avg_price,
            "top_listings": top_listings,
            "sample_size": len(results),
        }
    finally:
        if own_client:
            await client.aclose()
