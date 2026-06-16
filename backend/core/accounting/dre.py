from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.models import ExpenseCategory
from backend.infra.db.models import Expense, Sale


def _q2(d: Decimal) -> Decimal:
    return d.quantize(Decimal("0.01"))


def sale_cpv(sale: Sale) -> Decimal:
    return sale.cpv_override if sale.cpv_override is not None else sale.cpv_calc


async def compute_dre(session: AsyncSession, period_from: date, period_to: date) -> dict:
    """Agrega vendas confirmadas (por sold_at) e despesas (por incurred_at)."""
    sales = (
        await session.execute(
            select(Sale).where(
                Sale.is_sold.is_(True),
                Sale.sold_at.is_not(None),
                Sale.sold_at >= period_from,
                Sale.sold_at <= period_to,
            )
        )
    ).scalars().all()

    receita = sum((s.confirmed_revenue or Decimal(0) for s in sales), Decimal(0))
    cpv = sum((sale_cpv(s) for s in sales), Decimal(0))
    variaveis = sum((s.variable_costs for s in sales), Decimal(0))
    lucro_bruto = receita - cpv - variaveis

    expenses = (
        await session.execute(
            select(Expense).where(
                Expense.incurred_at >= period_from,
                Expense.incurred_at <= period_to,
            )
        )
    ).scalars().all()

    despesas = {cat.value: Decimal(0) for cat in ExpenseCategory}
    for e in expenses:
        despesas[e.category] = despesas.get(e.category, Decimal(0)) + e.amount
    total_despesas = sum(despesas.values(), Decimal(0))

    resultado = lucro_bruto - total_despesas
    margem = (resultado / receita * Decimal(100)) if receita > 0 else Decimal(0)

    return {
        "receita_bruta": _q2(receita),
        "cpv": _q2(cpv),
        "custos_variaveis": _q2(variaveis),
        "lucro_bruto": _q2(lucro_bruto),
        "despesas": {k: _q2(v) for k, v in despesas.items()},
        "total_despesas": _q2(total_despesas),
        "resultado_liquido": _q2(resultado),
        "margem_liquida_pct": _q2(margem),
    }
