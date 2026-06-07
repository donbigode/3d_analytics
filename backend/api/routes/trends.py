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
    ObservationOut,
    RankingRow,
    RefreshOut,
    SparkPoint,
    TopListing,
)
from backend.core.trends.scoring import score as compute_score
from backend.infra.db.models import KeywordIdea, KeywordObservation, User
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
    """Admin trigger — synchronously runs one collection pass."""
    n = await collect_once()
    return RefreshOut(observations_created=n)
