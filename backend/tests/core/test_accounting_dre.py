from datetime import date
from decimal import Decimal

import pytest

from backend.core.accounting.dre import compute_dre
from backend.core.models import ExpenseCategory, QuoteKind, QuoteStatus
from backend.infra.db import session as session_module
from backend.infra.db.models import Expense, MaterialConsumption, Quote, QuoteItem, Sale, Settings, Spool, User


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


@pytest.mark.asyncio
async def test_dre_v2_tax_recurring_and_unsold_stock():
    from datetime import date
    from backend.infra.db.models import (
        Expense, MaterialConsumption, Quote, QuoteItem, Sale, Settings, Spool, User,
    )
    from backend.core.models import ExpenseCategory, QuoteKind, QuoteStatus
    async with session_module.SessionFactory() as s:
        await s.merge(Settings(id=1, revenue_tax_pct=Decimal("10")))
        user = User(name="u", email="drev2@t.com", password_hash="x")
        s.add(user); await s.commit()
        q_sold = Quote(kind=QuoteKind.COMMERCIAL.value, user_id=user.id,
                       status=QuoteStatus.ENTREGUE.value, markup_pct=Decimal("0"),
                       min_charge=Decimal("0"))
        q_unsold = Quote(kind=QuoteKind.PERSONAL.value, user_id=user.id,
                         status=QuoteStatus.PRODUZIDO.value, markup_pct=Decimal("0"),
                         min_charge=Decimal("0"))
        s.add_all([q_sold, q_unsold]); await s.commit()
        s.add(Sale(quote_id=q_sold.id, quote_status="entregue", quote_kind="commercial",
                   quote_total=Decimal("1000"), cpv_calc=Decimal("0"), is_sold=True,
                   confirmed_revenue=Decimal("1000"), variable_costs=Decimal("0"),
                   sold_at=date(2026, 6, 10)))
        item = QuoteItem(quote_id=q_unsold.id, name="p", gcode_meta={}, quantity=1)
        spool = Spool(material_type="PLA", purchased_at=date(2026, 6, 1),
                      purchased_price=Decimal("100"), initial_grams=Decimal("1000"),
                      remaining_grams=Decimal("900"))
        s.add_all([item, spool]); await s.commit()
        from datetime import datetime, timezone
        s.add(MaterialConsumption(quote_item_id=item.id, spool_id=spool.id,
                                  grams_used=Decimal("100"), unit_cost_snapshot=Decimal("0.50"),
                                  consumed_at=datetime(2026, 6, 12, tzinfo=timezone.utc)))
        s.add(Expense(category=ExpenseCategory.OTHER.value, description="internet",
                      amount=Decimal("100"), incurred_at=date(2026, 6, 1), is_recurring=True))
        await s.commit()

    async with session_module.SessionFactory() as s:
        dre = await compute_dre(s, date(2026, 6, 1), date(2026, 6, 30))

    assert dre["receita_bruta"] == Decimal("1000.00")
    assert dre["impostos"] == Decimal("100.00")
    assert dre["receita_liquida"] == Decimal("900.00")
    assert dre["custo_estoque"] == Decimal("50.00")
    assert dre["despesas"]["other"] == Decimal("100.00")
    assert dre["resultado_liquido"] == Decimal("750.00")


@pytest.mark.asyncio
async def test_dre_recurring_replicates_per_month():
    from datetime import date
    from backend.infra.db.models import Expense, Settings
    from backend.core.models import ExpenseCategory
    async with session_module.SessionFactory() as s:
        await s.merge(Settings(id=1, revenue_tax_pct=Decimal("0")))
        s.add(Expense(category=ExpenseCategory.OTHER.value, description="aluguel",
                      amount=Decimal("100"), incurred_at=date(2026, 1, 1), is_recurring=True))
        await s.commit()
    async with session_module.SessionFactory() as s:
        dre = await compute_dre(s, date(2026, 1, 1), date(2026, 3, 31))
    assert dre["despesas"]["other"] == Decimal("300.00")
