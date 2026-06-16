from datetime import date
from decimal import Decimal

import pytest

from backend.core.accounting.dre import compute_dre
from backend.core.models import ExpenseCategory, QuoteKind, QuoteStatus
from backend.infra.db import session as session_module
from backend.infra.db.models import Expense, Quote, Sale, User


async def _mk_quote(s, user) -> Quote:
    """Sale.quote_id é NOT NULL com FK para quotes — cada Sale precisa de um Quote real."""
    q = Quote(kind=QuoteKind.COMMERCIAL.value, user_id=user.id,
              status=QuoteStatus.ENTREGUE.value, markup_pct=Decimal("0"), min_charge=Decimal("0"))
    s.add(q); await s.commit()
    return q


@pytest.mark.asyncio
async def test_dre_aggregates_sold_sales_and_expenses():
    async with session_module.SessionFactory() as s:
        user = User(name="u", email="dre@t.com", password_hash="x")
        s.add(user); await s.commit()
        q1 = await _mk_quote(s, user)
        q2 = await _mk_quote(s, user)
        q3 = await _mk_quote(s, user)
        # venda confirmada no período: receita 1000, cpv 300, variável 50
        s.add(Sale(quote_id=q1.id, quote_status="entregue", quote_total=Decimal("1000"),
                   cpv_calc=Decimal("300"), is_sold=True, confirmed_revenue=Decimal("1000"),
                   variable_costs=Decimal("50"), sold_at=date(2026, 6, 10)))
        # venda NÃO confirmada — não entra
        s.add(Sale(quote_id=q2.id, quote_status="aprovado", quote_total=Decimal("500"),
                   cpv_calc=Decimal("200"), is_sold=False, sold_at=None))
        # venda confirmada fora do período — não entra
        s.add(Sale(quote_id=q3.id, quote_status="entregue", quote_total=Decimal("800"),
                   cpv_calc=Decimal("100"), is_sold=True, confirmed_revenue=Decimal("800"),
                   variable_costs=Decimal("0"), sold_at=date(2026, 1, 1)))
        s.add(Expense(category=ExpenseCategory.PARTS.value, description="bico",
                      amount=Decimal("40"), incurred_at=date(2026, 6, 12)))
        await s.commit()

    async with session_module.SessionFactory() as s:
        dre = await compute_dre(s, date(2026, 6, 1), date(2026, 6, 30))

    assert dre["receita_bruta"] == Decimal("1000.00")
    assert dre["cpv"] == Decimal("300.00")
    assert dre["custos_variaveis"] == Decimal("50.00")
    assert dre["lucro_bruto"] == Decimal("650.00")
    assert dre["despesas"]["parts"] == Decimal("40.00")
    assert dre["resultado_liquido"] == Decimal("610.00")
    # margem = 610 / 1000
    assert dre["margem_liquida_pct"] == Decimal("61.00")
