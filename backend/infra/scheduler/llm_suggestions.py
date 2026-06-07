"""Daily LLM-driven suggestion job.

Each run:
  1. Loads provider config from Settings.
  2. Asks the provider for ``count`` keyword candidates.
  3. Embeds each candidate term + rationale.
  4. For each candidate, computes the max cosine similarity vs suggestions
     from the last 30 days. If >= ``AUTO_PROMOTE_THRESHOLD`` with at least
     ``AUTO_PROMOTE_MIN_NEIGHBORS`` neighbors, auto-promotes by creating a
     :class:`KeywordIdea` and linking it via ``promoted_keyword_id``.
  5. Writes one :class:`DataSourceRun` row per execution (success/error).

Gated by ``Settings.llm_suggestions_enabled``. The scheduler in
:mod:`backend.infra.scheduler.trends` is unchanged; this module exposes
``collect_llm_once`` for both the API trigger and the background loop.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.trends.embeddings import embed
from backend.core.trends.llm import SuggestionCandidate, resolve_provider
from backend.infra.db import session as session_module
from backend.infra.db.models import (
    DataSourceRun,
    KeywordIdea,
    LLMSuggestion,
    Settings,
)

logger = logging.getLogger(__name__)

AUTO_PROMOTE_THRESHOLD = 0.85
AUTO_PROMOTE_MIN_NEIGHBORS = 2
LOOKBACK_DAYS = 30


async def collect_llm_once(*, count: int = 10) -> dict:
    """Run one collection pass. Returns a small dict of stats."""
    started_at = datetime.now(timezone.utc)
    async with session_module.SessionFactory() as session:
        settings_row = await session.get(Settings, 1)
        if settings_row is None:
            return _record_run(session, "llm", started_at, "error",
                               error="settings row missing", items=0)

        provider = resolve_provider(
            preferred=settings_row.preferred_llm_provider,
            anthropic_key=settings_row.anthropic_api_key,
            gemini_key=settings_row.gemini_api_key,
        )
        if provider is None:
            return await _record_and_return(
                session, "llm", started_at, "error",
                error="no LLM provider configured", items=0,
            )

        try:
            candidates = await provider.suggest_trends(count=count)
        except Exception as e:  # noqa: BLE001
            return await _record_and_return(
                session, provider.name, started_at, "error",
                error=str(e), items=0,
            )

        if not candidates:
            return await _record_and_return(
                session, provider.name, started_at, "success",
                error=None, items=0, metadata={"note": "provider returned no candidates"},
            )

        # Embed terms + rationale together for richer recurrence signal.
        texts = [_text_for(c) for c in candidates]
        embeddings = await embed(texts)

        prior = await _load_recent_suggestions(session)
        created = await _persist_candidates(
            session, provider.name, candidates, embeddings, prior
        )
        return await _record_and_return(
            session, provider.name, started_at, "success",
            error=None, items=len(created),
            metadata={
                "auto_promoted": sum(1 for s in created if s.status == "auto_promoted"),
                "pending": sum(1 for s in created if s.status == "pending"),
            },
        )


def _text_for(c: SuggestionCandidate) -> str:
    return c.term if not c.rationale else f"{c.term} — {c.rationale}"


async def _load_recent_suggestions(session: AsyncSession) -> list[LLMSuggestion]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    res = await session.execute(
        select(LLMSuggestion).where(LLMSuggestion.suggested_at >= cutoff)
    )
    return list(res.scalars())


def _max_similarity(target: list[float], priors: Iterable[LLMSuggestion]) -> tuple[float, int]:
    """Return (max_similarity, neighbor_count_above_threshold)."""
    from backend.core.trends.embeddings import cosine_similarity

    best = 0.0
    neighbors = 0
    for p in priors:
        if not p.embedding:
            continue
        sim = cosine_similarity(target, list(p.embedding))
        if sim > best:
            best = sim
        if sim >= AUTO_PROMOTE_THRESHOLD:
            neighbors += 1
    return best, neighbors


async def _persist_candidates(
    session: AsyncSession,
    provider_name: str,
    candidates: list[SuggestionCandidate],
    embeddings: list[list[float]],
    priors: list[LLMSuggestion],
) -> list[LLMSuggestion]:
    out: list[LLMSuggestion] = []
    for cand, emb in zip(candidates, embeddings):
        max_sim, neighbors = _max_similarity(emb, priors)
        auto = (
            max_sim >= AUTO_PROMOTE_THRESHOLD
            and neighbors >= AUTO_PROMOTE_MIN_NEIGHBORS
        )
        promoted_id = None
        if auto:
            # Create the KeywordIdea unless term already exists (unique constraint).
            existing = await session.execute(
                select(KeywordIdea).where(KeywordIdea.term == cand.term)
            )
            ki = existing.scalar_one_or_none()
            if ki is None:
                ki = KeywordIdea(
                    term=cand.term,
                    notes=cand.rationale,
                    temporal_window=cand.temporal_window,
                    source_provider=provider_name,
                )
                session.add(ki)
                await session.flush()
            promoted_id = ki.id

        row = LLMSuggestion(
            term=cand.term,
            rationale=cand.rationale,
            provider=provider_name,
            embedding=emb,
            recurrence_score=Decimal(f"{max_sim:.4f}"),
            status="auto_promoted" if auto else "pending",
            promoted_keyword_id=promoted_id,
            temporal_window=cand.temporal_window,
        )
        session.add(row)
        out.append(row)
        # Append the new row to priors so the next candidate in the same batch
        # can rely on it (rare but cleaner).
        priors.append(row)

    await session.commit()
    for row in out:
        await session.refresh(row)
    return out


async def _record_and_return(
    session: AsyncSession,
    source: str,
    started_at: datetime,
    status: str,
    *,
    error: str | None,
    items: int,
    metadata: dict | None = None,
) -> dict:
    run = DataSourceRun(
        source=source,
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
        status=status,
        items_created=items,
        error_message=error,
        raw_metadata=metadata or None,
    )
    session.add(run)
    await session.commit()
    return {
        "source": source,
        "status": status,
        "items_created": items,
        "error": error,
        "metadata": metadata or {},
    }


def _record_run(session, source, started_at, status, *, error, items):
    """Sync fallback when even the session can't be opened. Returns shape only."""
    return {
        "source": source,
        "status": status,
        "items_created": items,
        "error": error,
        "metadata": {},
    }


# -- background loop ---------------------------------------------------------

async def run_forever(*, interval_hours: int = 24) -> None:
    """Daily loop. Exits silently when llm_suggestions_enabled becomes False."""
    while True:
        try:
            await collect_llm_once()
        except Exception as e:  # noqa: BLE001
            logger.exception("collect_llm_once raised: %s", e)
        await asyncio.sleep(interval_hours * 3600)


def start_background_task() -> asyncio.Task:
    return asyncio.create_task(run_forever())
