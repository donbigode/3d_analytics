"""Shared Mercado Livre lookup for LLM features (markup + pricing).

Lives outside the individual feature modules so both can ground their
prompts on the same live data without duplicating credential-handling +
token-refresh logic.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.trends.sources import mercadolivre as ml_source
from backend.infra.db.models import QuoteItem, Settings

logger = logging.getLogger(__name__)

_MIN_NAME_LEN = 4
_GENERIC = {"peca", "peça", "item", "test", "teste", "sample", "amostra"}


def _is_searchable(name: str) -> bool:
    n = (name or "").strip().lower()
    if len(n) < _MIN_NAME_LEN:
        return False
    base = n.split()[0].rstrip("0123456789-_")
    return base not in _GENERIC


async def gather_market_prices(
    session: AsyncSession,
    items: list[QuoteItem],
    *,
    max_queries: int = 5,
) -> tuple[list[dict], Decimal]:
    """Look up each item's name on Mercado Livre.

    Returns ``(observations, estimated_total)``. Each observation is a
    dict ``{term, avg_price, min_price, max_price, sold, sample}``.
    ``estimated_total`` is the sum of ``avg_price × quantity`` per item —
    a rough estimate of what the same bundle would cost in the marketplace.
    Empty list when ML credentials aren't configured or every name is too
    generic to search. Token refreshes are persisted back into Settings.
    """
    settings_row = await session.get(Settings, 1)
    if (
        not settings_row
        or not settings_row.meli_app_id
        or not settings_row.meli_client_secret
    ):
        return [], Decimal("0")

    creds = ml_source.MeliCredentials(
        app_id=settings_row.meli_app_id,
        client_secret=settings_row.meli_client_secret,
        access_token=settings_row.meli_access_token,
        token_expires_at=settings_row.meli_token_expires_at,
    )

    seen: dict[str, dict] = {}
    estimated_total = Decimal("0")
    queried = 0
    token_update = None
    for it in items:
        name = (it.name or "").strip()
        if not _is_searchable(name):
            continue
        key = name.lower()
        if key in seen:
            obs = seen[key]
        else:
            if queried >= max_queries:
                continue
            queried += 1
            try:
                stats, refresh = await ml_source.fetch_volume(name, creds=creds)
            except Exception as exc:  # noqa: BLE001
                logger.info("market lookup failed for %r: %s", name, exc)
                continue
            if refresh is not None:
                token_update = refresh
                creds = ml_source.MeliCredentials(
                    app_id=creds.app_id,
                    client_secret=creds.client_secret,
                    access_token=refresh.access_token,
                    token_expires_at=refresh.expires_at,
                )
            if not stats:
                continue
            avg = Decimal(str(stats.get("avg_price") or 0))
            if avg <= 0:
                continue
            # Derive a coarse floor/ceiling from the top_listings prices so the
            # LLM can quote a band instead of a single number.
            top = stats.get("top_listings") or []
            prices = [
                Decimal(str(t.get("price") or 0))
                for t in top
                if t.get("price")
            ]
            if prices:
                prices.sort()
                min_p = prices[0]
                max_p = prices[-1]
            else:
                min_p = avg
                max_p = avg
            obs = {
                "term": name,
                "avg_price": avg,
                "min_price": min_p,
                "max_price": max_p,
                "sold": int(Decimal(str(stats.get("sold_quantity") or 0))),
                "sample": int(stats.get("sample_size") or 0),
            }
            seen[key] = obs
        estimated_total += obs["avg_price"] * Decimal(int(it.quantity or 1))

    if token_update is not None:
        settings_row.meli_access_token = token_update.access_token
        settings_row.meli_token_expires_at = token_update.expires_at
        await session.commit()
        await session.refresh(settings_row)

    return list(seen.values()), estimated_total
