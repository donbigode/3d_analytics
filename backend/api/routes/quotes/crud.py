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
from backend.infra.db.models import Quote, QuoteItem, QuotePerson, QuoteService, User
from backend.infra.storage.gcodes import copy_gcode

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


@router.post("/{quote_id}/clone", response_model=QuoteOut, status_code=201)
async def clone_quote(
    quote_id: UUID,
    user: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    """Replica um orçamento como rascunho novo.

    O clone é um orçamento que ainda não aconteceu: status draft, sem
    timestamps de ciclo, sem consumo de material, sem evento de produção
    e sem linha no contábil. Copia configuração comercial, peças, serviços
    e o arquivo de gcode de cada item (para a pasta do novo orçamento,
    nunca compartilhando com a do original) — as fotos ficam para a
    próxima task.
    """
    orig = await session.get(Quote, quote_id)
    if not orig:
        raise HTTPException(404)

    novo = Quote(
        kind=orig.kind,
        client_id=orig.client_id,
        user_id=user.id,
        status=QuoteStatus.DRAFT,
        markup_pct=orig.markup_pct,
        min_charge=orig.min_charge,
        retail_mode=orig.retail_mode,
        notes=_notas_do_clone(orig),
    )
    session.add(novo)
    await session.flush()   # precisa do id para os itens (e, nas próximas tasks, as pastas de arquivo)

    itens_orig = (
        await session.execute(select(QuoteItem).where(QuoteItem.quote_id == orig.id))
    ).scalars().all()
    mapa_itens: dict[UUID, UUID] = {}
    for it in itens_orig:
        copia = QuoteItem(
            quote_id=novo.id,
            name=it.name,
            filename=copy_gcode(it.filename, novo.id),
            gcode_meta=dict(it.gcode_meta or {}),
            material_version_id=it.material_version_id,
            quantity=it.quantity,
            depreciation_rate_override=it.depreciation_rate_override,
            failure_rate_override=it.failure_rate_override,
            is_multi_color=it.is_multi_color,
            model_source_url=it.model_source_url,
            model_source_author=it.model_source_author,
            model_source_license=it.model_source_license,
            asset_id=it.asset_id,
        )
        session.add(copia)
        await session.flush()
        mapa_itens[it.id] = copia.id   # Task 3 usa este mapa para remapear as fotos

    servicos = (
        await session.execute(select(QuoteService).where(QuoteService.quote_id == orig.id))
    ).scalars().all()
    for qs in servicos:
        session.add(QuoteService(quote_id=novo.id, service_id=qs.service_id,
                                 quantity=qs.quantity, rate=qs.rate))

    pessoas = (
        await session.execute(select(QuotePerson).where(QuotePerson.quote_id == orig.id))
    ).scalars().all()
    for qp in pessoas:
        session.add(QuotePerson(quote_id=novo.id, person_id=qp.person_id))

    await session.commit()
    return await _quote_out(session, novo)


def _notas_do_clone(orig: Quote) -> str:
    """Rastreabilidade sem coluna nova: a origem vai na primeira linha
    das notas (decisão registrada na Spec 3 §3.5)."""
    cabecalho = f"Clone de #{orig.seq:04d}"
    return f"{cabecalho}\n{orig.notes}" if orig.notes else cabecalho
