"""Transições de status de orçamento (finalize, aprovar, produzir, ...).

As 7 transições "simples" (tudo exceto `produce`) são declaradas na tabela
`TRANSITIONS` e aplicadas por um handler genérico (`_apply_transition`), de
forma que o fluxo de status inteiro caiba numa tela. `produce` fica de fora
de propósito (spec §6): tem payload próprio (`ProduceRequest`), regra de
origem por tipo de orçamento e o efeito colateral pesado de debitar spools —
ver `apply_production` abaixo da tabela.
"""
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
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


# ---------- Tabela declarativa ----------

@dataclass(frozen=True)
class T:
    """Uma transição de status declarada.

    `from_`         estados de origem aceitos
    `to`            estado destino
    `stamp`         atributo de timestamp carimbado com _now(), se houver
    `kinds`         tipos de orçamento que aceitam a transição (None = todos)
    `kind_message`  mensagem literal (HTTP 400) quando `kinds` barra o tipo;
                    sem isso cai no genérico "transição não se aplica"
    `message`       mensagem literal (HTTP 409) quando o status não bate —
                    string fixa, ou uma função (quote) -> str para os casos
                    em que o texto depende do status atual; sem isso cai no
                    genérico "quote must be {estados} to {nome}"
    `guard`         validação extra; recebe (session, quote) e levanta HTTPException
    `on_apply`      efeito colateral; recebe (session, quote, payload)
    """
    from_: frozenset[QuoteStatus]
    to: QuoteStatus
    stamp: str | None = None
    kinds: frozenset[QuoteKind] | None = None
    kind_message: str | None = None
    message: "str | Callable[[Quote], str] | None" = None
    guard: Callable[..., Awaitable[None]] | None = None
    on_apply: Callable[..., Awaitable[None]] | None = None


async def _clear_finalized_at(session: AsyncSession, q: Quote, payload) -> None:
    """reopen: limpa o carimbo de finalização pra próxima finalize carimbar
    de novo (o ledger da task #99 mantém o histórico de auditoria)."""
    q.finalized_at = None


async def _record_success(session: AsyncSession, q: Quote, payload: CompleteRequest) -> None:
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


async def _record_failure(session: AsyncSession, q: Quote, payload: FailRequest) -> None:
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


# Espelha ao pé da letra a condição real do antigo t_cancel:
#   if q.status in (QuoteStatus.ENTREGUE, QuoteStatus.CANCELADO): 409
# _CANCELAVEIS é o complemento — todo o resto pode ser cancelado.
_CANCELAVEIS = frozenset(QuoteStatus) - {QuoteStatus.ENTREGUE, QuoteStatus.CANCELADO}


TRANSITIONS: dict[str, T] = {
    "finalize": T(
        from_=frozenset({QuoteStatus.DRAFT}),
        to=QuoteStatus.ORCADO,
        stamp="finalized_at",
        # Orçamentos pessoais pulam o pipeline comercial e vão direto pra
        # produção — mas produzir debita o estoque escolhido pelo usuário,
        # então eles finalizam via `produce` (que também carimba
        # finalized_at), não por aqui.
        kinds=frozenset({QuoteKind.COMMERCIAL}),
        kind_message=(
            "personal quotes are produced directly via the produce transition "
            "(select the spool for each item)"
        ),
        message="quote is not in draft",
        guard=_assert_materials_resolved,
    ),
    "reopen": T(
        # Manda um orçamento comercial finalizado de volta pro draft. Caso de
        # uso: cliente pediu peça extra depois do orçamento finalizado —
        # reabrimos o mesmo em vez de criar um irmão, pra manter histórico e
        # analytics juntos. Só a partir de 'orcado': depois de
        # aprovado/produzido/entregue, reabrir invalidaria eventos posteriores.
        from_=frozenset({QuoteStatus.ORCADO}),
        to=QuoteStatus.DRAFT,
        kinds=frozenset({QuoteKind.COMMERCIAL}),
        kind_message="only commercial quotes can be reopened",
        message=lambda q: (
            "quote can only be reopened from 'orcado' — current status: " + q.status
        ),
        on_apply=_clear_finalized_at,
    ),
    "approve": T(
        from_=frozenset({QuoteStatus.ORCADO}),
        to=QuoteStatus.APROVADO,
        stamp="approved_at",
        kinds=frozenset({QuoteKind.COMMERCIAL}),
        kind_message="only commercial quotes can be approved",
        message="quote is not in orcado",
    ),
    "complete": T(
        from_=frozenset({QuoteStatus.EM_PRODUCAO}),
        to=QuoteStatus.PRODUZIDO,
        stamp="produced_at",
        on_apply=_record_success,
        # mensagem: o genérico "quote must be em_producao to complete" já
        # bate com o texto original — sem override.
    ),
    "fail": T(
        from_=frozenset({QuoteStatus.EM_PRODUCAO}),
        to=QuoteStatus.FALHOU,
        on_apply=_record_failure,
        # idem: genérico "quote must be em_producao to fail" já bate.
    ),
    "deliver": T(
        from_=frozenset({QuoteStatus.PRODUZIDO}),
        to=QuoteStatus.ENTREGUE,
        stamp="delivered_at",
        kinds=frozenset({QuoteKind.COMMERCIAL}),
        kind_message="only commercial quotes can be delivered",
        message="quote must be produzido before deliver",
    ),
    "cancel": T(
        from_=_CANCELAVEIS,
        to=QuoteStatus.CANCELADO,
        stamp="cancelled_at",
        message="quote already finalized",
    ),
}


async def _apply_transition(session: AsyncSession, q: Quote, name: str, payload=None) -> None:
    t = TRANSITIONS[name]
    if t.kinds is not None and q.kind not in t.kinds:
        if t.kind_message is not None:
            raise HTTPException(400, t.kind_message)
        raise HTTPException(409, f"transição '{name}' não se aplica a orçamento {q.kind}")
    if q.status not in t.from_:
        if callable(t.message):
            raise HTTPException(409, t.message(q))
        if t.message is not None:
            raise HTTPException(409, t.message)
        esperados = ", ".join(sorted(s.value for s in t.from_))
        raise HTTPException(409, f"quote must be {esperados} to {name}")
    if t.guard:
        await t.guard(session, q)
    if t.on_apply:
        await t.on_apply(session, q, payload)
    q.status = t.to
    if t.stamp:
        setattr(q, t.stamp, _now())


# ---------- Endpoints ----------

@router.post("/{quote_id}/transitions/finalize", response_model=QuoteOut)
async def t_finalize(
    quote_id: UUID,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    q = await session.get(Quote, quote_id)
    if not q:
        raise HTTPException(404)
    await _apply_transition(session, q, "finalize")
    await session.commit()
    return await _quote_out(session, q)


@router.post("/{quote_id}/transitions/reopen", response_model=QuoteOut)
async def t_reopen(
    quote_id: UUID,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    q = await session.get(Quote, quote_id)
    if not q:
        raise HTTPException(404)
    await _apply_transition(session, q, "reopen")
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
    await _apply_transition(session, q, "approve")
    await session.commit()
    return await _quote_out(session, q)


async def apply_production(
    session: AsyncSession, q: Quote, assignments: list[ConsumptionAssignment]
) -> None:
    # Produce = "send to the printer queue": debit the selected spools and move
    # to em_producao (the FIFO in Capacidade, where Concluir/Falhar happen).
    # Commercial enters from aprovado; personal finalize-and-produces from draft.
    # Either kind can re-produce from falhou (a fresh cycle that debits again).
    # Fica fora de TRANSITIONS de propósito: payload próprio (assignments),
    # regra de origem por tipo e efeito colateral de debitar estoque.
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
    await _apply_transition(session, q, "complete", payload)
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
    await _apply_transition(session, q, "fail", payload)
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
    await _apply_transition(session, q, "deliver")
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
    await _apply_transition(session, q, "cancel")
    await session.commit()
    return await _quote_out(session, q)
