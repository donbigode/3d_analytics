"""Pessoas associadas a um orçamento pessoal.

Movido sem alteração de lógica a partir do antigo `backend/api/routes/quotes.py`.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import db_session, require_user
from backend.api.schemas.quotes import QuoteOut, QuotePeopleUpdate
from backend.api.routes.quotes._shared import _quote_out
from backend.core.models import QuoteKind
from backend.infra.db.models import Person, Quote, QuotePerson, User

router = APIRouter()


# ---------- Pessoas (projeto pessoal) ----------


@router.put("/{quote_id}/people", response_model=QuoteOut)
async def set_quote_people(
    quote_id: UUID,
    payload: QuotePeopleUpdate,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    q = await session.get(Quote, quote_id)
    if not q:
        raise HTTPException(404)
    if q.kind != QuoteKind.PERSONAL.value:
        raise HTTPException(400, "atribuição de pessoa só para orçamento pessoal")
    ids = [UUID(x) for x in payload.person_ids]
    if ids:
        found = set((await session.execute(
            select(Person.id).where(Person.id.in_(ids))
        )).scalars().all())
        if found != set(ids):
            raise HTTPException(400, "pessoa inexistente")
    await session.execute(delete(QuotePerson).where(QuotePerson.quote_id == q.id))
    for pid in ids:
        session.add(QuotePerson(quote_id=q.id, person_id=pid))
    await session.commit()
    return await _quote_out(session, q)
