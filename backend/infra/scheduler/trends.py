"""Daily collection scheduler for the trend radar.

`collect_once` is the unit of work — iterate every KeywordIdea, fetch Google
Trends + Mercado Livre, persist one KeywordObservation per metric. Built so
tests can call it directly with monkeypatched adapters.

`run_forever` wraps it in a sleep-24h loop. `start_background_task` is the
entrypoint used by the FastAPI startup hook.
"""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal

from sqlalchemy import select

from backend.core.trends.sources import google_trends as gt_source
from backend.core.trends.sources import mercadolivre as ml_source
from backend.infra.db import session as _db_session
from backend.infra.db.models import KeywordIdea, KeywordObservation

logger = logging.getLogger(__name__)

ONE_DAY_SECONDS = 24 * 60 * 60
INTER_TERM_SLEEP_SECONDS = 1.0


async def _collect_for_idea(session, idea: KeywordIdea) -> int:
    """Fetch + persist observations for a single keyword idea. Returns count."""
    inserted = 0

    # --- Google Trends ---
    try:
        interest = await gt_source.fetch_interest(idea.term)
    except Exception as exc:  # adapter should already be defensive, belt+suspenders
        logger.warning("google_trends raised for %s: %s", idea.term, exc)
        interest = None
    if interest is not None:
        session.add(
            KeywordObservation(
                keyword_id=idea.id,
                source="google_trends",
                metric="interest_score",
                value=Decimal(interest),
            )
        )
        inserted += 1

    # --- Mercado Livre ---
    try:
        ml = await ml_source.fetch_volume(idea.term)
    except Exception as exc:
        logger.warning("mercadolivre raised for %s: %s", idea.term, exc)
        ml = {}
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
        result = await session.execute(select(KeywordIdea))
        ideas = list(result.scalars())
        for i, idea in enumerate(ideas):
            try:
                total += await _collect_for_idea(session, idea)
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
