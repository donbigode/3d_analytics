"""Linhas de serviço de orçamento: adicionar e remover.

Movido sem alteração de lógica a partir do antigo `backend/api/routes/quotes.py`.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import db_session, require_user
from backend.api.schemas.quotes import QuoteOut, ServiceLineCreate
from backend.api.routes.quotes._shared import _quote_out
from backend.core.models import QuoteKind, QuoteStatus, ServiceKind
from backend.infra.db.models import Quote, QuoteService, Service, User

router = APIRouter()


# ---------- Services ----------

@router.post("/{quote_id}/services", response_model=QuoteOut, status_code=201)
async def add_service(
    quote_id: UUID,
    payload: ServiceLineCreate,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    q = await session.get(Quote, quote_id)
    if not q:
        raise HTTPException(404)
    if q.status != QuoteStatus.DRAFT:
        raise HTTPException(409, "quote not editable")
    svc = await session.get(Service, UUID(payload.service_id))
    if not svc:
        raise HTTPException(404, "service not found")
    if q.kind == QuoteKind.PERSONAL and svc.kind == ServiceKind.LABOR:
        raise HTTPException(400, "labor services not allowed on personal quotes")
    qs = QuoteService(
        quote_id=q.id,
        service_id=svc.id,
        quantity=payload.quantity,
        rate=payload.rate if payload.rate is not None else svc.default_rate,
    )
    session.add(qs)
    await session.commit()
    return await _quote_out(session, q)


@router.delete("/{quote_id}/services/{qs_id}", response_model=QuoteOut)
async def delete_service(
    quote_id: UUID,
    qs_id: UUID,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    q = await session.get(Quote, quote_id)
    if not q:
        raise HTTPException(404)
    if q.status != QuoteStatus.DRAFT:
        raise HTTPException(409, "quote not editable")
    qs = await session.get(QuoteService, qs_id)
    if not qs or qs.quote_id != quote_id:
        raise HTTPException(404)
    await session.delete(qs)
    await session.commit()
    return await _quote_out(session, q)
