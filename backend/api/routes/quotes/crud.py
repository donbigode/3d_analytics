"""CRUD de orçamento: criar, listar, obter, atualizar.

Movido sem alteração de lógica a partir do antigo `backend/api/routes/quotes.py`.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import db_session, require_user
from backend.api.schemas.quotes import QuoteCreate, QuoteOut, QuoteUpdate
from backend.api.routes.quotes._shared import _quote_out
from backend.core.models import QuoteKind, QuoteStatus
from backend.infra.db.models import Quote, User

router = APIRouter()


# ---------- CRUD ----------

@router.post("", response_model=QuoteOut, status_code=201)
async def create_quote(
    payload: QuoteCreate,
    user: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    q = Quote(
        kind=payload.kind,
        user_id=user.id,
        status=QuoteStatus.DRAFT,
        markup_pct=payload.markup_pct,
        min_charge=payload.min_charge,
        notes=payload.notes,
        client_id=UUID(payload.client_id) if payload.client_id else None,
    )
    session.add(q)
    await session.commit()
    await session.refresh(q)
    return await _quote_out(session, q)


@router.get("", response_model=list[QuoteOut])
async def list_quotes(
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
    status: QuoteStatus | None = Query(None),
    kind: QuoteKind | None = Query(None),
    client_id: str | None = Query(None),
):
    stmt = select(Quote).order_by(Quote.created_at.desc())
    if status:
        stmt = stmt.where(Quote.status == status)
    if kind:
        stmt = stmt.where(Quote.kind == kind)
    if client_id:
        stmt = stmt.where(Quote.client_id == UUID(client_id))
    res = await session.execute(stmt)
    out = []
    for q in res.scalars():
        out.append(await _quote_out(session, q))
    return out


@router.get("/{quote_id}", response_model=QuoteOut)
async def get_quote(
    quote_id: UUID,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    q = await session.get(Quote, quote_id)
    if not q:
        raise HTTPException(404)
    return await _quote_out(session, q)


@router.put("/{quote_id}", response_model=QuoteOut)
async def update_quote(
    quote_id: UUID,
    payload: QuoteUpdate,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    q = await session.get(Quote, quote_id)
    if not q:
        raise HTTPException(404)
    updates = payload.model_dump(exclude_unset=True)
    # ``retail_mode`` is a presentation toggle (which PDF layout to use),
    # so it stays editable after finalize. Every other field locks the
    # moment the quote leaves draft.
    presentation_only = {"retail_mode"}
    financial_updates = {k: v for k, v in updates.items() if k not in presentation_only}
    if financial_updates and q.status != QuoteStatus.DRAFT:
        raise HTTPException(409, "quote not editable")
    for k, v in updates.items():
        if k == "client_id" and v is not None:
            v = UUID(v)
        setattr(q, k, v)
    await session.commit()
    return await _quote_out(session, q)
