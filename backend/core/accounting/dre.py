from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.models import ExpenseCategory, QuoteKind
from backend.infra.db.models import (
    Expense, MaterialConsumption, Quote, QuoteItem, Sale, Settings,
)


def _q2(d: Decimal) -> Decimal:
    return d.quantize(Decimal("0.01"))


def sale_cpv(sale: Sale) -> Decimal:
    return sale.cpv_override if sale.cpv_override is not None else sale.cpv_calc


def _months(period_from: date, period_to: date) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    y, m = period_from.year, period_from.month
    while (y, m) <= (period_to.year, period_to.month):
        out.append((y, m))
        m += 1
        if m > 12:
            m = 1; y += 1
    return out


def _next_day(d: date) -> date:
    from datetime import timedelta
    return d + timedelta(days=1)


async def _custo_estoque(session: AsyncSession, period_from: date, period_to: date) -> Decimal:
    """Material de orçamentos COMERCIAIS não-vendidos no período (WIP que ainda pode vender).

    Vendidos saem (viram CPV da venda); pessoais saem (viram perda operacional pelo CPV
    cheio em ``_perda_operacional``, então o material deles não conta aqui de novo).
    """
    sold_quote_ids = set(
        (await session.execute(
            select(Sale.quote_id).where(Sale.is_sold.is_(True), Sale.is_stale.is_(False))
        )).scalars().all()
    )
    personal_quote_ids = set(
        (await session.execute(
            select(Quote.id).where(Quote.kind == QuoteKind.PERSONAL.value)
        )).scalars().all()
    )
    rows = (
        await session.execute(
            select(MaterialConsumption, QuoteItem.quote_id)
            .join(QuoteItem, MaterialConsumption.quote_item_id == QuoteItem.id)
            .where(
                MaterialConsumption.consumed_at >= period_from,
                MaterialConsumption.consumed_at < _next_day(period_to),
            )
        )
    ).all()
    total = Decimal(0)
    for cons, quote_id in rows:
        if quote_id in sold_quote_ids or quote_id in personal_quote_ids:
            continue
        total += cons.grams_used * cons.unit_cost_snapshot
    return total


async def _perda_operacional(session: AsyncSession, period_from: date, period_to: date) -> Decimal:
    """Uso pessoal produzido e NÃO vendido = perda operacional pelo CPV cheio.

    Atribuído ao período pela data de produção (menor ``consumed_at`` da baixa de
    material do orçamento); sem baixa, cai no ``created_at`` da venda.
    """
    sales = (
        await session.execute(
            select(Sale).where(
                Sale.quote_kind == QuoteKind.PERSONAL.value,
                Sale.is_sold.is_(False),
                Sale.is_stale.is_(False),
            )
        )
    ).scalars().all()
    if not sales:
        return Decimal(0)

    sale_by_quote = {s.quote_id: s for s in sales}
    prod_rows = (
        await session.execute(
            select(QuoteItem.quote_id, func.min(MaterialConsumption.consumed_at))
            .join(MaterialConsumption, MaterialConsumption.quote_item_id == QuoteItem.id)
            .where(QuoteItem.quote_id.in_(sale_by_quote.keys()))
            .group_by(QuoteItem.quote_id)
        )
    ).all()
    prod_date = {qid: dt for qid, dt in prod_rows}

    total = Decimal(0)
    for quote_id, sale in sale_by_quote.items():
        dt = prod_date.get(quote_id) or sale.created_at
        d = dt.date() if hasattr(dt, "date") else dt
        if period_from <= d <= period_to:
            total += sale_cpv(sale)
    return total


async def compute_dre(session: AsyncSession, period_from: date, period_to: date) -> dict:
    settings_row = await session.get(Settings, 1)
    tax_pct = settings_row.revenue_tax_pct if settings_row else Decimal(0)

    sales = (
        await session.execute(
            select(Sale).where(
                Sale.is_sold.is_(True),
                Sale.is_stale.is_(False),
                Sale.sold_at.is_not(None),
                Sale.sold_at >= period_from,
                Sale.sold_at <= period_to,
            )
        )
    ).scalars().all()

    receita = sum((s.confirmed_revenue or Decimal(0) for s in sales), Decimal(0))
    impostos = receita * tax_pct / Decimal(100)
    receita_liquida = receita - impostos
    cpv = sum((sale_cpv(s) for s in sales), Decimal(0))
    variaveis = sum((s.variable_costs for s in sales), Decimal(0))
    lucro_bruto = receita_liquida - cpv - variaveis

    expenses = (await session.execute(select(Expense))).scalars().all()
    months = _months(period_from, period_to)
    despesas = {cat.value: Decimal(0) for cat in ExpenseCategory}
    for e in expenses:
        if e.is_recurring:
            start = (e.incurred_at.year, e.incurred_at.month)
            n = sum(1 for ym in months if ym >= start)
            despesas[e.category] = despesas.get(e.category, Decimal(0)) + e.amount * n
        elif period_from <= e.incurred_at <= period_to:
            despesas[e.category] = despesas.get(e.category, Decimal(0)) + e.amount

    custo_estoque = await _custo_estoque(session, period_from, period_to)
    perda_operacional = await _perda_operacional(session, period_from, period_to)
    total_despesas = sum(despesas.values(), Decimal(0)) + custo_estoque + perda_operacional

    resultado = lucro_bruto - total_despesas
    margem = (resultado / receita * Decimal(100)) if receita > 0 else Decimal(0)

    return {
        "receita_bruta": _q2(receita),
        "impostos": _q2(impostos),
        "receita_liquida": _q2(receita_liquida),
        "cpv": _q2(cpv),
        "custos_variaveis": _q2(variaveis),
        "lucro_bruto": _q2(lucro_bruto),
        "despesas": {k: _q2(v) for k, v in despesas.items()},
        "custo_estoque": _q2(custo_estoque),
        "perda_operacional": _q2(perda_operacional),
        "total_despesas": _q2(total_despesas),
        "resultado_liquido": _q2(resultado),
        "margem_liquida_pct": _q2(margem),
    }
