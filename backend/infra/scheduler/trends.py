"""Daily collection scheduler for the trend radar.

`collect_once` iterates every KeywordIdea and fans out across the six data
sources (Google Trends, Wikipedia, Reddit, Mercado Livre, YouTube). Each
source's pass — across all ideas — is logged as a single ``DataSourceRun``
so the /trends "Fontes" panel surfaces success/error and last_error_message.

Previously only the LLM scheduler logged runs, so Google Trends / Reddit /
etc looked perpetually "never executed" in the UI even after a collect.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.trends.sources import google_trends as gt_source
from backend.core.trends.sources import mercadolivre as ml_source
from backend.core.trends.sources import reddit as reddit_source
from backend.core.trends.sources import wikipedia as wiki_source
from backend.core.trends.sources import youtube as yt_source
from backend.infra.db import session as _db_session
from backend.infra.db.models import DataSourceRun, KeywordIdea, KeywordObservation, Settings

logger = logging.getLogger(__name__)

ONE_DAY_SECONDS = 24 * 60 * 60
# Bumped from 1s to 5s — Google Trends rate-limits aggressively at ~5 req/min
# from a single IP and the 1s gap was getting us 429'd within the first batch.
INTER_TERM_SLEEP_SECONDS = 5.0


@dataclass
class _SourceStat:
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    items_created: int = 0
    errors: list[str] = field(default_factory=list)
    skipped: bool = False  # source disabled (no creds/key); don't log a run

    def record_error(self, term: str, exc: object) -> None:
        msg = str(exc)
        self.errors.append(f"{term}: {msg[:120]}")


def _build_meli_creds(settings_row: Settings | None) -> ml_source.MeliCredentials | None:
    if not settings_row or not settings_row.meli_app_id or not settings_row.meli_client_secret:
        return None
    return ml_source.MeliCredentials(
        app_id=settings_row.meli_app_id,
        client_secret=settings_row.meli_client_secret,
        access_token=settings_row.meli_access_token,
        token_expires_at=settings_row.meli_token_expires_at,
    )


def _build_reddit_creds(settings_row: Settings | None) -> reddit_source.RedditCredentials | None:
    if not settings_row or not settings_row.reddit_client_id or not settings_row.reddit_client_secret:
        return None
    return reddit_source.RedditCredentials(
        client_id=settings_row.reddit_client_id,
        client_secret=settings_row.reddit_client_secret,
        access_token=settings_row.reddit_access_token,
        token_expires_at=settings_row.reddit_token_expires_at,
    )


async def _collect_google_trends(session, idea, *, window, stat: _SourceStat) -> None:
    # Sticky rate-limit flag — once we see 429, skip the rest of the batch.
    if getattr(stat, "rate_limited", False):
        return
    try:
        interest = await gt_source.fetch_interest(idea.term, window=window)
    except gt_source.GoogleTrendsRateLimited as exc:
        stat.errors.append(
            "Google Trends rate-limited (HTTP 429). Próxima coleta amanhã — "
            "ou troque o IP de saída (proxy / VPN) se for urgente."
        )
        stat.rate_limited = True
        return
    except Exception as exc:  # belt+suspenders
        stat.record_error(idea.term, exc)
        return
    if interest is None:
        # pytrends returns None for empty series too; record as a soft miss
        stat.errors.append(f"{idea.term}: empty series")
        return
    session.add(
        KeywordObservation(
            keyword_id=idea.id,
            source="google_trends",
            metric="interest_score",
            value=Decimal(interest),
            raw_payload={"window": window},
        )
    )
    stat.items_created += 1


async def _collect_wikipedia(session, idea, *, window, stat: _SourceStat) -> None:
    try:
        wiki_views = await wiki_source.fetch_interest(idea.term, window=window)
    except Exception as exc:
        stat.record_error(idea.term, exc)
        return
    if wiki_views is None:
        stat.errors.append(f"{idea.term}: no article")
        return
    session.add(
        KeywordObservation(
            keyword_id=idea.id,
            source="wikipedia",
            metric="pageviews_mean",
            value=Decimal(wiki_views),
            raw_payload={"window": window},
        )
    )
    stat.items_created += 1


async def _collect_reddit(
    session,
    idea,
    *,
    creds,
    settings_row,
    stat: _SourceStat,
):
    """Returns potentially refreshed creds so the caller can reuse on next ideas.

    When credentials are missing we skip silently (no DataSourceRun row). When
    they're present but the API rejects them (401), we surface the message
    once via stat.errors and stop hammering Reddit for subsequent ideas — the
    auth failure is sticky for the rest of the collect pass.
    """
    if creds is None:
        return None
    # If a prior idea already saw an auth failure, bail out.
    if getattr(stat, "auth_failed", False):
        return creds
    try:
        rd, token_update = await reddit_source.fetch_engagement(idea.term, creds=creds)
    except reddit_source.RedditAuthError as exc:
        # Record once and pin the auth-failed flag so subsequent ideas skip.
        stat.errors.append(str(exc))
        stat.auth_failed = True
        return creds
    except Exception as exc:
        stat.record_error(idea.term, exc)
        return creds

    # Persist token refresh on Settings + propagate to the in-memory creds
    if token_update and settings_row is not None:
        settings_row.reddit_access_token = token_update.access_token
        settings_row.reddit_token_expires_at = token_update.expires_at
        creds = reddit_source.RedditCredentials(
            client_id=creds.client_id,
            client_secret=creds.client_secret,
            access_token=token_update.access_token,
            token_expires_at=token_update.expires_at,
        )

    if not rd:
        stat.errors.append(f"{idea.term}: empty response")
        return creds
    posts_score = rd.get("posts_score")
    posts_comments = rd.get("posts_comments")
    if posts_score is not None:
        session.add(
            KeywordObservation(
                keyword_id=idea.id,
                source="reddit",
                metric="posts_score",
                value=Decimal(posts_score),
                raw_payload={
                    "posts_count": rd.get("posts_count", 0),
                    "top_posts": rd.get("top_posts", []),
                },
            )
        )
        stat.items_created += 1
    if posts_comments is not None:
        session.add(
            KeywordObservation(
                keyword_id=idea.id,
                source="reddit",
                metric="posts_comments",
                value=Decimal(posts_comments),
            )
        )
        stat.items_created += 1
    return creds


async def _collect_mercadolivre(
    session, idea, *, creds, settings_row, stat: _SourceStat
):
    if creds is None:
        return None
    try:
        ml, token_update = await ml_source.fetch_volume(idea.term, creds=creds)
    except Exception as exc:
        stat.record_error(idea.term, exc)
        return creds

    if token_update and settings_row is not None:
        settings_row.meli_access_token = token_update.access_token
        settings_row.meli_token_expires_at = token_update.expires_at
        creds = ml_source.MeliCredentials(
            app_id=creds.app_id,
            client_secret=creds.client_secret,
            access_token=token_update.access_token,
            token_expires_at=token_update.expires_at,
        )

    if not ml:
        stat.errors.append(f"{idea.term}: empty response")
        return creds
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
        stat.items_created += 1
    if price is not None:
        session.add(
            KeywordObservation(
                keyword_id=idea.id,
                source="mercadolivre",
                metric="avg_price",
                value=Decimal(price),
            )
        )
        stat.items_created += 1
    return creds


async def _collect_youtube(session, idea, *, api_key, stat: _SourceStat) -> None:
    if not api_key:
        return
    try:
        yt = await yt_source.fetch_views(idea.term, api_key=api_key)
    except Exception as exc:
        stat.record_error(idea.term, exc)
        return
    if not yt:
        stat.errors.append(f"{idea.term}: empty response")
        return
    views = yt.get("views_total")
    if views is None:
        return
    session.add(
        KeywordObservation(
            keyword_id=idea.id,
            source="youtube",
            metric="views_total",
            value=Decimal(views),
            raw_payload={
                "videos_count": yt.get("videos_count", 0),
                "top_videos": yt.get("top_videos", []),
            },
        )
    )
    stat.items_created += 1


def _finalize_run(session: AsyncSession, source: str, stat: _SourceStat, *, terms_total: int) -> None:
    if stat.skipped:
        return
    finished_at = datetime.now(timezone.utc)
    # success when at least one observation came through; otherwise error if any
    # term raised, otherwise success-empty (a soft no-op — still a "success" run).
    if stat.items_created > 0:
        status = "success"
    elif stat.errors:
        status = "error"
    else:
        status = "success"
    err = "; ".join(stat.errors[:5]) if stat.errors else None
    session.add(
        DataSourceRun(
            source=source,
            started_at=stat.started_at,
            finished_at=finished_at,
            status=status,
            items_created=stat.items_created,
            error_message=err,
            raw_metadata={
                "terms_processed": terms_total,
                "soft_errors": len(stat.errors),
            },
        )
    )


async def collect_once() -> int:
    """Run one collection pass over every KeywordIdea. Returns total inserted.

    Logs one DataSourceRun per source (aggregating across all ideas).
    """
    total = 0
    async with _db_session.SessionFactory() as session:
        settings_row = await session.get(Settings, 1)
        meli_creds = _build_meli_creds(settings_row)
        reddit_creds = _build_reddit_creds(settings_row)
        youtube_key = settings_row.youtube_api_key if settings_row else None

        result = await session.execute(select(KeywordIdea))
        ideas = list(result.scalars())

        gt_stat = _SourceStat()
        wiki_stat = _SourceStat()
        reddit_stat = _SourceStat()
        ml_stat = _SourceStat()
        yt_stat = _SourceStat()

        for i, idea in enumerate(ideas):
            window = idea.temporal_window or "month"
            try:
                await _collect_google_trends(session, idea, window=window, stat=gt_stat)
                await _collect_wikipedia(session, idea, window=window, stat=wiki_stat)
                reddit_creds = await _collect_reddit(
                    session, idea, creds=reddit_creds,
                    settings_row=settings_row, stat=reddit_stat,
                )
                meli_creds = await _collect_mercadolivre(
                    session, idea, creds=meli_creds,
                    settings_row=settings_row, stat=ml_stat,
                )
                await _collect_youtube(session, idea, api_key=youtube_key, stat=yt_stat)
            except Exception as exc:
                logger.exception("collect failed for %s: %s", idea.term, exc)
            if i < len(ideas) - 1:
                await asyncio.sleep(INTER_TERM_SLEEP_SECONDS)

        total = (
            gt_stat.items_created
            + wiki_stat.items_created
            + reddit_stat.items_created
            + ml_stat.items_created
            + yt_stat.items_created
        )

        # When credentials are missing we mark the source as skipped — no
        # DataSourceRun row, so the Fontes panel shows "—" instead of polluting
        # the "Itens 24h" / "Erros 7d" counters with non-events.
        if not reddit_creds:
            reddit_stat.skipped = True
        if not meli_creds:
            ml_stat.skipped = True
        if not youtube_key:
            yt_stat.skipped = True

        # Log one DataSourceRun per source.
        _finalize_run(session, "google_trends", gt_stat, terms_total=len(ideas))
        _finalize_run(session, "wikipedia", wiki_stat, terms_total=len(ideas))
        _finalize_run(session, "reddit", reddit_stat, terms_total=len(ideas))
        _finalize_run(session, "mercadolivre", ml_stat, terms_total=len(ideas))
        _finalize_run(session, "youtube", yt_stat, terms_total=len(ideas))

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
