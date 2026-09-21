"""Transições de status de orçamento (finalize, aprovar, produzir, ...).

Movido sem alteração de lógica a partir do antigo `backend/api/routes/quotes.py`.
Nota: a Task 8 (próxima do mesmo lote) converte estas 8 transições numa tabela
declarativa. Este módulo, por enquanto, é apenas a mudança mecânica.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import db_session, require_user
from backend.api.schemas.quotes import (
    CompleteRequest,
    ConsumptionAssignment,
    FailRequest,
    ProduceRequest,
    QuoteOut,
)
from backend.api.routes.quotes._shared import (
    _assert_materials_resolved,
    _cycle_context_and_grams,
    _now,
    _quote_out,
)
from backend.core.models import ProductionOutcome, QuoteKind, QuoteStatus, SpoolStatus
from backend.core.quote_service import grams_for_item
from backend.infra.db.models import (
    MaterialConsumption,
    MaterialVersion,
    ProductionEvent,
    Quote,
    QuoteItem,
    Spool,
    User,
)

router = APIRouter()


# ---------- Transitions ----------

@router.post("/{quote_id}/transitions/finalize", response_model=QuoteOut)
async def t_finalize(
    quote_id: UUID,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    q = await session.get(Quote, quote_id)
    if not q:
        raise HTTPException(404)
    # Personal projects skip the commercial pipeline and go straight to
    # production — but production debits the stock the user selects, so they
    # finalize through `produce` (which also stamps finalized_at), not here.
    if q.kind == QuoteKind.PERSONAL:
        raise HTTPException(
            400,
            "personal quotes are produced directly via the produce transition "
            "(select the spool for each item)",
        )
    if q.status != QuoteStatus.DRAFT:
        raise HTTPException(409, "quote is not in draft")
    await _assert_materials_resolved(session, q)
    q.finalized_at = _now()
    q.status = QuoteStatus.ORCADO
    await session.commit()
    return await _quote_out(session, q)


@router.post("/{quote_id}/transitions/reopen", response_model=QuoteOut)
async def t_reopen(
    quote_id: UUID,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    """Send a finalized commercial quote back to draft.

    Use case: the client asked for an extra piece after the quote was
    finalized. Rather than create a sibling, we reopen the same one so
    discussion history and analytics stay together. Allowed only from
    ``orcado`` — once a quote is approved/produced/delivered, reopening
    would invalidate downstream events, so we refuse those.
    """
    q = await session.get(Quote, quote_id)
    if not q:
        raise HTTPException(404)
    if q.kind != QuoteKind.COMMERCIAL:
        raise HTTPException(400, "only commercial quotes can be reopened")
    if q.status != QuoteStatus.ORCADO:
        raise HTTPException(
            409, "quote can only be reopened from 'orcado' — current status: " + q.status
        )
    q.status = QuoteStatus.DRAFT
    # Clear the finalize timestamp so the next finalize stamps fresh; the
    # ledger (task #99) will keep the audit history.
    q.finalized_at = None
    await session.commit()
    return await _quote_out(session, q)


@router.post("/{quote_id}/transitions/approve", response_model=QuoteOut)
async def t_approve(
    quote_id: UUID,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    q = await session.get(Quote, quote_id)
    if not q:
        raise HTTPException(404)
    if q.kind != QuoteKind.COMMERCIAL:
        raise HTTPException(400, "only commercial quotes can be approved")
    if q.status != QuoteStatus.ORCADO:
        raise HTTPException(409, "quote is not in orcado")
    q.status = QuoteStatus.APROVADO
    q.approved_at = _now()
    await session.commit()
    return await _quote_out(session, q)


async def apply_production(
    session: AsyncSession, q: Quote, assignments: list[ConsumptionAssignment]
) -> None:
    # Produce = "send to the printer queue": debit the selected spools and move
    # to em_producao (the FIFO in Capacidade, where Concluir/Falhar happen).
    # Commercial enters from aprovado; personal finalize-and-produces from draft.
    # Either kind can re-produce from falhou (a fresh cycle that debits again).
    if q.kind == QuoteKind.COMMERCIAL:
        if q.status not in (QuoteStatus.APROVADO, QuoteStatus.FALHOU):
            raise HTTPException(409, "quote must be aprovado (ou falhou) before produce")
    elif q.kind == QuoteKind.PERSONAL:
        if q.status not in (QuoteStatus.DRAFT, QuoteStatus.FALHOU):
            raise HTTPException(409, "personal quote must be in draft (ou falhou) to produce")
        await _assert_materials_resolved(session, q)
        if q.finalized_at is None:
            q.finalized_at = _now()
    else:
        raise HTTPException(400, "unsupported quote kind for produce")

    for assign in assignments:
        it = await session.get(QuoteItem, UUID(assign.quote_item_id))
        sp = await session.get(Spool, UUID(assign.spool_id))
        if not it or it.quote_id != q.id or not sp:
            raise HTTPException(400, "invalid assignment")
        mv = await session.get(MaterialVersion, it.material_version_id)
        if assign.grams is not None and assign.grams > 0:
            # Override direto: debita exatamente o informado (total da linha).
            grams = assign.grams
        else:
            if assign.filament_m is not None and assign.filament_m > 0:
                # Override de metragem: persiste no item para custo/analytics.
                meta = dict(it.gcode_meta or {})
                meta["filament_m"] = float(assign.filament_m)
                it.gcode_meta = meta
            grams = grams_for_item(it.gcode_meta, mv.density_g_cm3, it.quantity)
        if grams <= 0:
            raise HTTPException(
                409,
                f"item '{it.name}' has no filament length (filament_m=0); "
                "informe a metragem ou as gramas a debitar para produzir",
            )
        if sp.remaining_grams < grams:
            raise HTTPException(409, f"spool {sp.id} has insufficient grams")
        sp.remaining_grams = sp.remaining_grams - grams
        if sp.remaining_grams <= 0:
            sp.status = SpoolStatus.EMPTY
        unit_cost = sp.purchased_price / sp.initial_grams
        session.add(
            MaterialConsumption(
                quote_item_id=it.id,
                spool_id=sp.id,
                grams_used=grams,
                unit_cost_snapshot=unit_cost,
            )
        )
    q.status = QuoteStatus.EM_PRODUCAO


@router.post("/{quote_id}/transitions/produce", response_model=QuoteOut)
async def t_produce(
    quote_id: UUID,
    payload: ProduceRequest,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    q = await session.get(Quote, quote_id)
    if not q:
        raise HTTPException(404)
    await apply_production(session, q, payload.consumption)
    await session.commit()
    return await _quote_out(session, q)


@router.post("/{quote_id}/transitions/complete", response_model=QuoteOut)
async def t_complete(
    quote_id: UUID,
    payload: CompleteRequest,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    q = await session.get(Quote, quote_id)
    if not q:
        raise HTTPException(404)
    if q.status != QuoteStatus.EM_PRODUCAO:
        raise HTTPException(409, "quote must be em_producao to complete")
    ctx, _grams = await _cycle_context_and_grams(session, q)
    session.add(
        ProductionEvent(
            quote_id=q.id,
            kind=q.kind,
            outcome=ProductionOutcome.SUCCESS,
            attempts=max(1, payload.attempts),
            context=ctx,
            grams_wasted=None,
        )
    )
    q.status = QuoteStatus.PRODUZIDO
    q.produced_at = _now()
    await session.commit()
    return await _quote_out(session, q)


@router.post("/{quote_id}/transitions/fail", response_model=QuoteOut)
async def t_fail(
    quote_id: UUID,
    payload: FailRequest,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    q = await session.get(Quote, quote_id)
    if not q:
        raise HTTPException(404)
    if q.status != QuoteStatus.EM_PRODUCAO:
        raise HTTPException(409, "quote must be em_producao to fail")
    desc = (payload.failure_description or "").strip()
    if not desc:
        raise HTTPException(400, "failure_description is required")
    ctx, grams = await _cycle_context_and_grams(session, q)
    session.add(
        ProductionEvent(
            quote_id=q.id,
            kind=q.kind,
            outcome=ProductionOutcome.FAILURE,
            attempts=max(1, payload.attempts),
            failure_description=desc,
            context=ctx,
            grams_wasted=grams,
        )
    )
    q.status = QuoteStatus.FALHOU
    await session.commit()
    return await _quote_out(session, q)


@router.post("/{quote_id}/transitions/deliver", response_model=QuoteOut)
async def t_deliver(
    quote_id: UUID,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    q = await session.get(Quote, quote_id)
    if not q:
        raise HTTPException(404)
    if q.kind != QuoteKind.COMMERCIAL:
        raise HTTPException(400, "only commercial quotes can be delivered")
    if q.status != QuoteStatus.PRODUZIDO:
        raise HTTPException(409, "quote must be produzido before deliver")
    q.status = QuoteStatus.ENTREGUE
    q.delivered_at = _now()
    await session.commit()
    return await _quote_out(session, q)


@router.post("/{quote_id}/transitions/cancel", response_model=QuoteOut)
async def t_cancel(
    quote_id: UUID,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    q = await session.get(Quote, quote_id)
    if not q:
        raise HTTPException(404)
    if q.status in (QuoteStatus.ENTREGUE, QuoteStatus.CANCELADO):
        raise HTTPException(409, "quote already finalized")
    q.status = QuoteStatus.CANCELADO
    q.cancelled_at = _now()
    await session.commit()
    return await _quote_out(session, q)
