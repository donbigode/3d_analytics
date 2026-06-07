"""Daily collection scheduler for the trend radar.

`collect_once` is the unit of work — iterate every KeywordIdea, fetch Google
Trends + Mercado Livre with the idea's temporal_window, persist one
KeywordObservation per metric.

`run_forever` wraps it in a sleep-24h loop. `start_background_task` is the
entrypoint used by the FastAPI startup hook.
"""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.trends.sources import google_trends as gt_source
from backend.core.trends.sources import mercadolivre as ml_source
from backend.infra.db import session as _db_session
from backend.infra.db.models import KeywordIdea, KeywordObservation, Settings

logger = logging.getLogger(__name__)

ONE_DAY_SECONDS = 24 * 60 * 60
INTER_TERM_SLEEP_SECONDS = 1.0


def _build_meli_creds(settings_row: Settings | None) -> ml_source.MeliCredentials | None:
    if not settings_row or not settings_row.meli_app_id or not settings_row.meli_client_secret:
        return None
    return ml_source.MeliCredentials(
        app_id=settings_row.meli_app_id,
        client_secret=settings_row.meli_client_secret,
        access_token=settings_row.meli_access_token,
        token_expires_at=settings_row.meli_token_expires_at,
    )


async def _collect_for_idea(
    session: AsyncSession,
    idea: KeywordIdea,
    *,
    meli_creds: ml_source.MeliCredentials | None,
    settings_row: Settings | None,
) -> int:
    """Fetch + persist observations for a single keyword idea. Returns count."""
    inserted = 0
    window = idea.temporal_window or "month"

    # --- Google Trends ---
    try:
        interest = await gt_source.fetch_interest(idea.term, window=window)
    except Exception as exc:  # belt+suspenders
        logger.warning("google_trends raised for %s: %s", idea.term, exc)
        interest = None
    if interest is not None:
        session.add(
            KeywordObservation(
                keyword_id=idea.id,
                source="google_trends",
                metric="interest_score",
                value=Decimal(interest),
                raw_payload={"window": window},
            )
        )
        inserted += 1

    # --- Mercado Livre ---
    try:
        ml, token_update = await ml_source.fetch_volume(idea.term, creds=meli_creds)
    except Exception as exc:
        logger.warning("mercadolivre raised for %s: %s", idea.term, exc)
        ml, token_update = {}, None

    # Persist refreshed token (if any) before continuing so the next idea
    # in this loop pass uses the new token.
    if token_update and settings_row is not None:
        settings_row.meli_access_token = token_update.access_token
        settings_row.meli_token_expires_at = token_update.expires_at
        meli_creds = ml_source.MeliCredentials(
            app_id=meli_creds.app_id if meli_creds else "",
            client_secret=meli_creds.client_secret if meli_creds else "",
            access_token=token_update.access_token,
            token_expires_at=token_update.expires_at,
        )

    if ml:
        sold = ml.get("sold_quantity")
        price = ml.get("avg_price")
        if sold is not None:
            session.add(
                KeywordObservation(
                    keyword_id=idea.id,
                    source="mercadolivre",
                    metric="sold_quantity",
                    value=Decimal(sold),
                    raw_payload={
                        "top_listings": ml.get("top_listings", []),
                        "sample_size": ml.get("sample_size", 0),
                    },
                )
            )
            inserted += 1
        if price is not None:
            session.add(
                KeywordObservation(
                    keyword_id=idea.id,
                    source="mercadolivre",
                    metric="avg_price",
                    value=Decimal(price),
                )
            )
            inserted += 1

    return inserted


async def collect_once() -> int:
    """Run one collection pass over every KeywordIdea. Returns total inserted."""
    total = 0
    async with _db_session.SessionFactory() as session:
        settings_row = await session.get(Settings, 1)
        meli_creds = _build_meli_creds(settings_row)

        result = await session.execute(select(KeywordIdea))
        ideas = list(result.scalars())
        for i, idea in enumerate(ideas):
            try:
                total += await _collect_for_idea(
                    session, idea, meli_creds=meli_creds, settings_row=settings_row
                )
            except Exception as exc:
                logger.exception("collect failed for %s: %s", idea.term, exc)
            if i < len(ideas) - 1:
                await asyncio.sleep(INTER_TERM_SLEEP_SECONDS)
        await session.commit()
    return total


async def run_forever() -> None:
    """Background loop: sleep 24h, collect, repeat. Catches all errors."""
    while True:
        try:
            await collect_once()
        except Exception as exc:  # pragma: no cover - defensive top-level
            logger.exception("collect_once crashed: %s", exc)
        await asyncio.sleep(ONE_DAY_SECONDS)


def start_background_task() -> asyncio.Task:
    return asyncio.create_task(run_forever())
