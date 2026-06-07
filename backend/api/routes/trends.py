"""Trend radar HTTP surface.

Endpoints:
  - GET/POST/DELETE /trends/ideas        — keyword CRUD
  - GET            /trends/ideas/{id}/observations  — time series for charting
  - GET            /trends/ranking       — scored + sparkline rows
  - POST           /trends/refresh       — admin trigger (sync collection)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import db_session, require_user
from backend.api.schemas.trends import (
    KeywordIdeaCreate,
    KeywordIdeaOut,
    LLMRefreshOut,
    ObservationOut,
    RankingRow,
    RefreshOut,
    SourceMetric,
    SourceMetricsOut,
    SparkPoint,
    SuggestionOut,
    SuggestionPromoteOut,
    TopListing,
)
from backend.core.trends.scoring import score as compute_score
from backend.infra.db.models import (
    DataSourceRun,
    KeywordIdea,
    KeywordObservation,
    LLMSuggestion,
    Settings,
    User,
)
from backend.infra.scheduler.llm_suggestions import collect_llm_once
from backend.infra.scheduler.trends import collect_once

router = APIRouter()


def _idea_out(k: KeywordIdea) -> KeywordIdeaOut:
    return KeywordIdeaOut(
        id=str(k.id), term=k.term, notes=k.notes, created_at=k.created_at
    )


@router.get("/ideas", response_model=list[KeywordIdeaOut])
async def list_ideas(
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    res = await session.execute(select(KeywordIdea).order_by(KeywordIdea.created_at.desc()))
    return [_idea_out(k) for k in res.scalars()]


@router.post("/ideas", response_model=KeywordIdeaOut, status_code=201)
async def create_idea(
    payload: KeywordIdeaCreate,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    term = payload.term.strip()
    if not term:
        raise HTTPException(400, "term cannot be empty")
    k = KeywordIdea(term=term, notes=payload.notes)
    session.add(k)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(409, "term already exists")
    await session.refresh(k)
    return _idea_out(k)


@router.delete("/ideas/{idea_id}", status_code=204)
async def delete_idea(
    idea_id: UUID,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    k = await session.get(KeywordIdea, idea_id)
    if not k:
        raise HTTPException(404)
    await session.delete(k)
    await session.commit()


@router.get("/ideas/{idea_id}/observations", response_model=list[ObservationOut])
async def list_observations(
    idea_id: UUID,
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = Query(None),
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    k = await session.get(KeywordIdea, idea_id)
    if not k:
        raise HTTPException(404)
    stmt = select(KeywordObservation).where(KeywordObservation.keyword_id == idea_id)
    if from_:
        stmt = stmt.where(KeywordObservation.taken_at >= from_)
    if to:
        stmt = stmt.where(KeywordObservation.taken_at <= to)
    stmt = stmt.order_by(KeywordObservation.taken_at.asc())
    res = await session.execute(stmt)
    out = []
    for o in res.scalars():
        out.append(
            ObservationOut(
                id=str(o.id),
                keyword_id=str(o.keyword_id),
                source=o.source,
                metric=o.metric,
                value=o.value,
                raw_payload=o.raw_payload,
                taken_at=o.taken_at,
            )
        )
    return out


def _latest_by(observations: list[KeywordObservation], source: str, metric: str):
    """Most recent observation for (source, metric) or None."""
    best = None
    for o in observations:
        if o.source == source and o.metric == metric:
            if best is None or o.taken_at > best.taken_at:
                best = o
    return best


@router.get("/ranking", response_model=list[RankingRow])
async def ranking(
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    res = await session.execute(select(KeywordIdea))
    ideas = list(res.scalars())
    if not ideas:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    obs_res = await session.execute(
        select(KeywordObservation)
        .where(
            and_(
                KeywordObservation.keyword_id.in_([i.id for i in ideas]),
                KeywordObservation.taken_at >= cutoff,
            )
        )
        .order_by(KeywordObservation.taken_at.asc())
    )
    obs_by_kid: dict[Any, list[KeywordObservation]] = {}
    for o in obs_res.scalars():
        obs_by_kid.setdefault(o.keyword_id, []).append(o)

    rows: list[RankingRow] = []
    for idea in ideas:
        obs = obs_by_kid.get(idea.id, [])
        interest_o = _latest_by(obs, "google_trends", "interest_score")
        vol_o = _latest_by(obs, "mercadolivre", "sold_quantity")
        price_o = _latest_by(obs, "mercadolivre", "avg_price")

        interest = interest_o.value if interest_o else None
        vol = vol_o.value if vol_o else None
        price = price_o.value if price_o else None
        s = compute_score(interest, vol, price)

        # Sparkline = chronological interest_score points over last 30d.
        sparkline = [
            SparkPoint(taken_at=o.taken_at, value=o.value)
            for o in obs
            if o.source == "google_trends" and o.metric == "interest_score"
        ]

        top_listings: list[TopListing] = []
        if vol_o and isinstance(vol_o.raw_payload, dict):
            raw_listings = vol_o.raw_payload.get("top_listings") or []
            for ln in raw_listings[:5]:
                if isinstance(ln, dict):
                    top_listings.append(
                        TopListing(
                            title=ln.get("title") or "",
                            price=ln.get("price"),
                            sold=int(ln.get("sold") or 0),
                            permalink=ln.get("permalink"),
                        )
                    )

        rows.append(
            RankingRow(
                id=str(idea.id),
                term=idea.term,
                score=s,
                interest=interest,
                ml_volume=vol,
                ml_avg_price=price,
                sparkline=sparkline,
                top_listings=top_listings,
            )
        )

    rows.sort(key=lambda r: r.score, reverse=True)
    return rows


@router.post("/refresh", response_model=RefreshOut)
async def refresh(_: User = Depends(require_user)):
    """Admin trigger — synchronously runs one Google Trends + ML pass."""
    n = await collect_once()
    return RefreshOut(observations_created=n)


# ---------------- LLM suggestions ----------------


def _suggestion_out(s: LLMSuggestion) -> SuggestionOut:
    return SuggestionOut(
        id=str(s.id),
        term=s.term,
        rationale=s.rationale,
        provider=s.provider,
        recurrence_score=s.recurrence_score,
        status=s.status,
        promoted_keyword_id=str(s.promoted_keyword_id) if s.promoted_keyword_id else None,
        suggested_at=s.suggested_at,
    )


@router.get("/suggestions", response_model=list[SuggestionOut])
async def list_suggestions(
    status: str = Query("pending"),
    limit: int = Query(50, ge=1, le=200),
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    """List LLM suggestions filtered by status (default: pending)."""
    stmt = (
        select(LLMSuggestion)
        .where(LLMSuggestion.status == status)
        .order_by(desc(LLMSuggestion.suggested_at))
        .limit(limit)
    )
    res = await session.execute(stmt)
    return [_suggestion_out(s) for s in res.scalars()]


@router.post("/suggestions/{suggestion_id}/promote", response_model=SuggestionPromoteOut)
async def promote_suggestion(
    suggestion_id: UUID,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    """Manually promote a pending suggestion to a KeywordIdea."""
    s = await session.get(LLMSuggestion, suggestion_id)
    if not s:
        raise HTTPException(404)
    if s.status != "pending":
        raise HTTPException(409, f"suggestion already {s.status}")
    # KeywordIdea has unique term; reuse if exists.
    existing = await session.execute(select(KeywordIdea).where(KeywordIdea.term == s.term))
    ki = existing.scalar_one_or_none()
    if ki is None:
        ki = KeywordIdea(term=s.term, notes=s.rationale)
        session.add(ki)
        await session.flush()
    s.status = "promoted"
    s.promoted_keyword_id = ki.id
    await session.commit()
    return SuggestionPromoteOut(
        suggestion_id=str(s.id), keyword_id=str(ki.id), term=ki.term
    )


@router.post("/suggestions/{suggestion_id}/dismiss", response_model=SuggestionOut)
async def dismiss_suggestion(
    suggestion_id: UUID,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    s = await session.get(LLMSuggestion, suggestion_id)
    if not s:
        raise HTTPException(404)
    if s.status != "pending":
        raise HTTPException(409, f"suggestion already {s.status}")
    s.status = "dismissed"
    await session.commit()
    return _suggestion_out(s)


@router.post("/llm-refresh", response_model=LLMRefreshOut)
async def llm_refresh(
    count: int = Query(10, ge=1, le=30),
    _: User = Depends(require_user),
):
    """Admin trigger — synchronously runs one LLM suggestion pass."""
    result = await collect_llm_once(count=count)
    return LLMRefreshOut(**result)


# ---------------- Source metrics ----------------


@router.get("/sources", response_model=SourceMetricsOut)
async def list_sources(
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    """Aggregated per-source metrics for the /trends sources panel."""
    settings_row = await session.get(Settings, 1)

    sources_config: list[tuple[str, bool]] = [
        ("google_trends", True),
        ("mercadolivre", True),
        ("anthropic", bool(settings_row and settings_row.anthropic_api_key)),
        ("gemini", bool(settings_row and settings_row.gemini_api_key)),
        ("llm", bool(settings_row and settings_row.llm_suggestions_enabled)),
    ]

    now = datetime.now(timezone.utc)
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)

    rows: list[SourceMetric] = []
    for source, enabled in sources_config:
        last_run = await session.execute(
            select(DataSourceRun)
            .where(DataSourceRun.source == source)
            .order_by(desc(DataSourceRun.started_at))
            .limit(1)
        )
        last = last_run.scalar_one_or_none()

        recent_24h = (
            await session.execute(
                select(DataSourceRun).where(
                    DataSourceRun.source == source,
                    DataSourceRun.started_at >= last_24h,
                )
            )
        ).scalars().all()

        recent_7d = (
            await session.execute(
                select(DataSourceRun).where(
                    DataSourceRun.source == source,
                    DataSourceRun.started_at >= last_7d,
                )
            )
        ).scalars().all()

        runs_24h = len(recent_24h)
        items_created_24h = sum(r.items_created for r in recent_24h)
        errors_7d = sum(1 for r in recent_7d if r.status == "error")
        durations = [
            int((r.finished_at - r.started_at).total_seconds() * 1000)
            for r in recent_7d
            if r.finished_at
        ]
        avg_duration_ms_7d = int(sum(durations) / len(durations)) if durations else None

        rows.append(
            SourceMetric(
                source=source,
                enabled=enabled,
                last_run_at=last.started_at if last else None,
                last_status=last.status if last else None,
                runs_24h=runs_24h,
                items_created_24h=items_created_24h,
                errors_7d=errors_7d,
                avg_duration_ms_7d=avg_duration_ms_7d,
            )
        )

    return SourceMetricsOut(sources=rows)
