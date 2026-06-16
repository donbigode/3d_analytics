from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import db_session, require_user
from backend.api.schemas.accounting import (
    DreOut, ExpenseCreate, ExpenseOut, ExpenseUpdate, SaleOut, SaleUpdate, SyncOut,
)
from backend.core.accounting.dre import compute_dre
from backend.core.accounting.sync import sync_sales
from backend.infra.db.models import Expense, Sale, User

router = APIRouter()


def _sale_out(s: Sale) -> SaleOut:
    return SaleOut(
        id=str(s.id), quote_id=str(s.quote_id), quote_status=s.quote_status,
        quote_total=s.quote_total, cpv_calc=s.cpv_calc,
        client_id=str(s.client_id) if s.client_id else None,
        is_stale=s.is_stale, is_sold=s.is_sold, confirmed_revenue=s.confirmed_revenue,
        variable_costs=s.variable_costs, cpv_override=s.cpv_override,
        sold_at=s.sold_at, notes=s.notes,
    )


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
    is_sold: bool | None = Query(None),
    is_stale: bool | None = Query(None),
):
    await sync_sales(session)  # lazy: materializa ao abrir a aba
    stmt = select(Sale).order_by(Sale.created_at.desc())
    if is_sold is not None:
        stmt = stmt.where(Sale.is_sold.is_(is_sold))
    if is_stale is not None:
        stmt = stmt.where(Sale.is_stale.is_(is_stale))
    rows = (await session.execute(stmt)).scalars().all()
    return [_sale_out(s) for s in rows]


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
    # Uma venda confirmada precisa de receita e data: preenche defaults se
    # ficaram nulos (inclusive se o cliente mandou null explícito).
    if sale.is_sold:
        if sale.confirmed_revenue is None:
            sale.confirmed_revenue = sale.quote_total
        if sale.sold_at is None:
            sale.sold_at = datetime.now(timezone.utc).date()
    await session.commit(); await session.refresh(sale)
    return _sale_out(sale)


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
