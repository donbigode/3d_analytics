"""Mercado Livre search adapter — OAuth-only since 2024.

ML deprecated anonymous public access for ``/sites/MLB/search``. Reads now
require a Bearer token from an App registered at
https://developers.mercadolivre.com.br/devcenter. This adapter implements the
``client_credentials`` grant (no user consent, no redirect) — the user pastes
App ID + Client Secret on the /config page and we exchange them for a 6h
access_token.

Returns aggregated stats over the top-20 results for the given term:
  - sold_quantity: sum of `sold_quantity` across results
  - avg_price:     mean of `price` across results
  - top_listings:  first 5 with title/price/sold/permalink (UI display)
  - sample_size:   number of results aggregated

The fetch_volume() return signature is ``(stats_dict, token_update_or_None)``:
when a refresh happened, the caller persists ``token_update`` back to Settings.
Returns ``({}, None)`` when credentials are missing or any HTTP/parse failure.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import httpx

logger = logging.getLogger(__name__)

ML_SEARCH_URL = "https://api.mercadolibre.com/sites/MLB/search"
ML_TOKEN_URL = "https://api.mercadolibre.com/oauth/token"
_TIMEOUT = httpx.Timeout(15.0)


@dataclass(frozen=True)
class MeliCredentials:
    app_id: str
    client_secret: str
    access_token: str | None = None
    token_expires_at: datetime | None = None


@dataclass(frozen=True)
class MeliTokenUpdate:
    access_token: str
    expires_at: datetime


def _is_token_valid(creds: MeliCredentials) -> bool:
    if not creds.access_token or not creds.token_expires_at:
        return False
    # 60s safety margin.
    return creds.token_expires_at > datetime.now(timezone.utc) + timedelta(seconds=60)


async def _refresh_token(
    creds: MeliCredentials, *, client: httpx.AsyncClient
) -> MeliTokenUpdate | None:
    try:
        r = await client.post(
            ML_TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": creds.app_id,
                "client_secret": creds.client_secret,
            },
            headers={"accept": "application/json"},
        )
        r.raise_for_status()
        body = r.json()
    except Exception as exc:
        logger.warning("mercadolivre token refresh failed: %s", exc)
        return None

    access_token = body.get("access_token")
    expires_in = int(body.get("expires_in") or 0)
    if not access_token or expires_in <= 0:
        logger.warning("mercadolivre token refresh returned no token")
        return None
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    return MeliTokenUpdate(access_token=access_token, expires_at=expires_at)


async def fetch_volume(
    term: str,
    *,
    creds: MeliCredentials | None = None,
    client: httpx.AsyncClient | None = None,
) -> tuple[dict[str, Any], MeliTokenUpdate | None]:
    """Search ML and aggregate top-20 results.

    Returns ``(stats, token_update)``. ``token_update`` is populated only when
    a refresh happened; the caller persists it back to Settings.
    """

    if creds is None or not creds.app_id or not creds.client_secret:
        return {}, None

    own_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=_TIMEOUT)

    token_update: MeliTokenUpdate | None = None
    try:
        access_token = creds.access_token
        if not _is_token_valid(creds):
            refreshed = await _refresh_token(creds, client=client)
            if refreshed is None:
                return {}, None
            access_token = refreshed.access_token
            token_update = refreshed

        try:
            r = await client.get(
                ML_SEARCH_URL,
                params={"q": term, "limit": 20},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            r.raise_for_status()
            data = r.json()
        except Exception as exc:
            logger.warning("mercadolivre search failed for %r: %s", term, exc)
            return {}, token_update

        results = data.get("results") or []
        if not results:
            return (
                {
                    "sold_quantity": Decimal("0"),
                    "avg_price": Decimal("0"),
                    "top_listings": [],
                    "sample_size": 0,
                },
                token_update,
            )

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
        return (
            {
                "sold_quantity": sold_sum,
                "avg_price": avg_price,
                "top_listings": top_listings,
                "sample_size": len(results),
            },
            token_update,
        )
    finally:
        if own_client:
            await client.aclose()
