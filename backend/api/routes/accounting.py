from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import db_session, require_user
from backend.api.schemas.accounting import (
    DreOut, ExpenseCreate, ExpenseOut, ExpenseUpdate, FactRow, MonthlyDreOut,
    ProfitabilityOut, SaleOut, SaleUpdate, SyncOut,
)
from backend.core.accounting.dre import compute_dre
from backend.core.accounting.facts import compute_facts, sale_items_label, sale_items_label_map
from backend.core.accounting.export_xlsx import build_dre_xlsx
from backend.core.accounting.monthly import compute_dre_monthly
from backend.core.accounting.profitability import compute_profitability
from backend.core.accounting.sync import sync_sales
from backend.core.models import QuoteKind
from backend.infra.db.models import (
    Client, Expense, MaterialConsumption, Person, Quote, QuoteItem, QuotePerson, Sale, User,
)

router = APIRouter()


def _sale_out(s: Sale, itens_label: str = "", client_name: str | None = None,
              quote_seq: int = 0, produced_on: date | None = None,
              people: list[str] | None = None, *, loss_on: date) -> SaleOut:
    return SaleOut(
        id=str(s.id), quote_id=str(s.quote_id), quote_seq=quote_seq,
        quote_kind=s.quote_kind, produced_on=produced_on, loss_on=loss_on,
        quote_status=s.quote_status,
        quote_total=s.quote_total, cpv_calc=s.cpv_calc,
        client_id=str(s.client_id) if s.client_id else None,
        is_stale=s.is_stale, is_sold=s.is_sold, confirmed_revenue=s.confirmed_revenue,
        variable_costs=s.variable_costs, cpv_override=s.cpv_override,
        sold_at=s.sold_at, notes=s.notes, itens_label=itens_label, client_name=client_name,
        people=people or [],
    )


async def _client_name(session: AsyncSession, s: Sale) -> str | None:
    if not s.client_id:
        return None
    c = await session.get(Client, s.client_id)
    return c.name if c else None


async def _produced_on_map(session: AsyncSession, quote_ids: list[UUID]) -> dict[UUID, date]:
    """Menor consumed_at por orçamento — mesmo critério de atribuição de
    período que _perda_operacional usa no DRE (backend/core/accounting/dre.py).
    Uma query para todos os quote_ids, evitando N+1."""
    if not quote_ids:
        return {}
    rows = (
        await session.execute(
            select(QuoteItem.quote_id, func.min(MaterialConsumption.consumed_at))
            .join(MaterialConsumption, MaterialConsumption.quote_item_id == QuoteItem.id)
            .where(QuoteItem.quote_id.in_(quote_ids))
            .group_by(QuoteItem.quote_id)
        )
    ).all()
    return {qid: (dt.date() if hasattr(dt, "date") else dt) for qid, dt in rows}


async def _people_map(session: AsyncSession, quote_ids: list[UUID]) -> dict[UUID, list[str]]:
    """Nomes das pessoas atribuídas a cada orçamento (quote_people ↔ people),
    em ordem alfabética. Uma query em lote pra toda a listagem — mesmo padrão
    de _produced_on_map, evitando N+1."""
    if not quote_ids:
        return {}
    rows = (
        await session.execute(
            select(QuotePerson.quote_id, Person.name)
            .join(Person, Person.id == QuotePerson.person_id)
            .where(QuotePerson.quote_id.in_(quote_ids))
            .order_by(Person.name)
        )
    ).all()
    people_por_quote: dict[UUID, list[str]] = {}
    for qid, name in rows:
        people_por_quote.setdefault(qid, []).append(name)
    return people_por_quote


def _loss_on(sale: Sale, produced_on: date | None) -> date:
    """Mesmo critério de dre.py:_perda_operacional — produced_on (menor
    consumed_at da baixa de material) se houver, senão sale.created_at.
    Ao contrário de produced_on, é sempre um valor (toda Sale tem created_at),
    por isso é o campo certo pra decidir se a linha pesa na perda operacional
    do período; produced_on continua sendo só a data de produção de fato."""
    if produced_on is not None:
        return produced_on
    dt = sale.created_at
    return dt.date() if hasattr(dt, "date") else dt


async def _quote_seq(session: AsyncSession, quote_id: UUID) -> int:
    return (await session.execute(select(Quote.seq).where(Quote.id == quote_id))).scalar() or 0


def _expense_out(e: Expense) -> ExpenseOut:
    return ExpenseOut(id=str(e.id), category=e.category, description=e.description,
                      amount=e.amount, incurred_at=e.incurred_at, is_recurring=e.is_recurring)


@router.post("/sync", response_model=SyncOut)
async def run_sync(_: User = Depends(require_user), session: AsyncSession = Depends(db_session)):
    return SyncOut(**await sync_sales(session))


@router.get("/sales", response_model=list[SaleOut])
async def list_sales(
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
    kind: QuoteKind | None = Query(None),
    is_sold: bool | None = Query(None),
    is_stale: bool | None = Query(None),
):
    # GET é só leitura — o sync agora é explícito via POST /accounting/sync
    # (Spec 2 §6.1). Antes, cada abertura da aba/atualização recalculava o
    # custo de todo orçamento aprovado.
    stmt = select(Sale).order_by(Sale.created_at.desc())
    if kind is not None:
        stmt = stmt.where(Sale.quote_kind == kind.value)
    if is_sold is not None:
        stmt = stmt.where(Sale.is_sold.is_(is_sold))
    if is_stale is not None:
        stmt = stmt.where(Sale.is_stale.is_(is_stale))
    rows = (await session.execute(stmt)).scalars().all()
    # Resolve quote_seq, nome de cliente e rótulo de itens de todas as linhas
    # em queries em lote (uma cada) — antes eram um N+1 por linha via
    # sale_items_label/_client_name.
    quote_ids = [s.quote_id for s in rows]
    client_ids = [s.client_id for s in rows if s.client_id]
    seq_por_quote = dict(
        (await session.execute(
            select(Quote.id, Quote.seq).where(Quote.id.in_(quote_ids))
        )).all()
    ) if quote_ids else {}
    nome_por_cliente = dict(
        (await session.execute(
            select(Client.id, Client.name).where(Client.id.in_(client_ids))
        )).all()
    ) if client_ids else {}
    produced_on_por_quote = await _produced_on_map(session, quote_ids)
    label_por_quote = await sale_items_label_map(session, quote_ids)
    people_por_quote = await _people_map(session, quote_ids)
    return [
        _sale_out(
            s,
            itens_label=label_por_quote.get(s.quote_id, ""),
            client_name=nome_por_cliente.get(s.client_id),
            # Sale.quote_id é not-null/unique/CASCADE — toda venda tem
            # orçamento vivo, então o .get() nunca cai no default 0.
            # Mantido como defesa, não como caminho esperado.
            quote_seq=seq_por_quote.get(s.quote_id, 0),
            produced_on=produced_on_por_quote.get(s.quote_id),
            people=people_por_quote.get(s.quote_id),
            loss_on=_loss_on(s, produced_on_por_quote.get(s.quote_id)),
        )
        for s in rows
    ]


@router.patch("/sales/{sale_id}", response_model=SaleOut)
async def update_sale(
    sale_id: UUID, payload: SaleUpdate,
    _: User = Depends(require_user), session: AsyncSession = Depends(db_session),
):
    sale = await session.get(Sale, sale_id)
    if not sale:
        raise HTTPException(404)
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(sale, k, v)

    if sale.is_sold:
        # A receita tem palpite óbvio (o total do orçamento); a data não.
        # Antes daqui, sold_at era preenchido com hoje em silêncio e a venda
        # caía no mês corrente do DRE mesmo tendo ocorrido em outro.
        if sale.confirmed_revenue is None:
            sale.confirmed_revenue = sale.quote_total
        if sale.sold_at is None:
            raise HTTPException(422, "informe a data da venda")
    else:
        # Desmarcar limpa: receita confirmada sem venda não significa nada, e
        # deixar a data para trás fazia remarcar ressuscitar o mês errado.
        sale.sold_at = None
        sale.confirmed_revenue = None

    await session.commit()
    await session.refresh(sale)
    # produced_on também deve vir preenchido aqui: quem chama o PATCH atualiza
    # a linha da tabela de forma otimista com esta resposta, e um None
    # apagaria a coluna mesmo quando a produção existe (mesma classe de bug
    # já corrigida para itens_label/client_name).
    produced_on = (await _produced_on_map(session, [sale.quote_id])).get(sale.quote_id)
    # people também precisa vir preenchido aqui pela mesma razão de
    # produced_on acima: a atualização otimista da linha usa esta resposta.
    people = (await _people_map(session, [sale.quote_id])).get(sale.quote_id)
    return _sale_out(
        sale,
        await sale_items_label(session, sale),
        await _client_name(session, sale),
        quote_seq=await _quote_seq(session, sale.quote_id),
        produced_on=produced_on,
        people=people,
        loss_on=_loss_on(sale, produced_on),
    )


@router.get("/expenses", response_model=list[ExpenseOut])
async def list_expenses(_: User = Depends(require_user), session: AsyncSession = Depends(db_session)):
    rows = (
        await session.execute(select(Expense).order_by(Expense.incurred_at.desc()))
    ).scalars().all()
    return [_expense_out(e) for e in rows]


@router.post("/expenses", response_model=ExpenseOut, status_code=201)
async def create_expense(
    payload: ExpenseCreate,
    _: User = Depends(require_user), session: AsyncSession = Depends(db_session),
):
    e = Expense(category=payload.category.value, description=payload.description,
                amount=payload.amount, incurred_at=payload.incurred_at,
                is_recurring=payload.is_recurring)
    session.add(e); await session.commit(); await session.refresh(e)
    return _expense_out(e)


@router.patch("/expenses/{expense_id}", response_model=ExpenseOut)
async def update_expense(
    expense_id: UUID, payload: ExpenseUpdate,
    _: User = Depends(require_user), session: AsyncSession = Depends(db_session),
):
    e = await session.get(Expense, expense_id)
    if not e:
        raise HTTPException(404)
    data = payload.model_dump(exclude_unset=True)
    if "category" in data and data["category"] is not None:
        data["category"] = data["category"].value
    for k, v in data.items():
        setattr(e, k, v)
    await session.commit(); await session.refresh(e)
    return _expense_out(e)


@router.delete("/expenses/{expense_id}", status_code=204)
async def delete_expense(
    expense_id: UUID,
    _: User = Depends(require_user), session: AsyncSession = Depends(db_session),
):
    e = await session.get(Expense, expense_id)
    if not e:
        raise HTTPException(404)
    await session.delete(e); await session.commit()


@router.get("/dre", response_model=DreOut)
async def dre(
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
    from_: date = Query(..., alias="from"),
    to: date = Query(...),
):
    return DreOut(**await compute_dre(session, from_, to))


@router.get("/dre/monthly", response_model=list[MonthlyDreOut])
async def dre_monthly(
    _: User = Depends(require_user), session: AsyncSession = Depends(db_session),
    from_: date = Query(..., alias="from"), to: date = Query(...),
):
    return [MonthlyDreOut(**row) for row in await compute_dre_monthly(session, from_, to)]


@router.get("/dre/export.xlsx")
async def dre_export(
    _: User = Depends(require_user), session: AsyncSession = Depends(db_session),
    from_: date = Query(..., alias="from"), to: date = Query(...),
):
    data = await build_dre_xlsx(session, from_, to)
    headers = {"Content-Disposition": f'attachment; filename="dre_{from_}_{to}.xlsx"'}
    return StreamingResponse(
        iter([data]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


@router.get("/profitability", response_model=ProfitabilityOut)
async def profitability(
    _: User = Depends(require_user), session: AsyncSession = Depends(db_session),
    from_: date = Query(..., alias="from"), to: date = Query(...),
):
    return ProfitabilityOut(**await compute_profitability(session, from_, to))


@router.get("/facts", response_model=list[FactRow])
async def facts(
    _: User = Depends(require_user), session: AsyncSession = Depends(db_session),
    from_: date = Query(..., alias="from"), to: date = Query(...),
):
    return [FactRow(**row) for row in await compute_facts(session, from_, to)]
