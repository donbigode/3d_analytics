"""O rodapé da aba Uso pessoal tem que bater com perda_operacional do DRE.

Divergência aqui é bug: os dois usam o mesmo critério de período (data de
produção = menor consumed_at) e a mesma fonte (linhas Sale pessoais não
vendidas e não arquivadas).

Semeadura no mesmo padrão de test_dre_personal_unsold_is_operational_loss_full_cpv,
em backend/tests/core/test_accounting_dre.py. Vive em tests/api (não tests/core)
porque exercita uma chamada HTTP real (GET /accounting/sales) — é o diretório
que tem o fixture auth_client.
"""
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from backend.core.accounting.dre import compute_dre
from backend.core.models import QuoteKind, QuoteStatus
from backend.infra.db import session as session_module
from backend.infra.db.models import (
    MaterialConsumption, Quote, QuoteItem, Sale, Settings, Spool, User,
)

PERIODO_DE = date(2026, 9, 1)
PERIODO_ATE = date(2026, 9, 30)


@pytest.mark.asyncio
async def test_soma_da_aba_pessoal_bate_com_perda_operacional(auth_client):
    async with session_module.SessionFactory() as s:
        await s.merge(Settings(id=1, revenue_tax_pct=Decimal("0")))
        user = User(name="u", email="abapessoal@t.com", password_hash="x")
        s.add(user)
        await s.commit()

        # Pessoal produzido e NÃO vendido: entra na perda pelo CPV cheio (70).
        q_perdido = Quote(kind=QuoteKind.PERSONAL.value, user_id=user.id,
                          status=QuoteStatus.PRODUZIDO.value, markup_pct=Decimal("0"),
                          min_charge=Decimal("0"))
        # Pessoal VENDIDO: sai da perda e vira receita.
        q_vendido = Quote(kind=QuoteKind.PERSONAL.value, user_id=user.id,
                          status=QuoteStatus.ENTREGUE.value, markup_pct=Decimal("0"),
                          min_charge=Decimal("0"))
        s.add_all([q_perdido, q_vendido])
        await s.commit()

        s.add(Sale(quote_id=q_perdido.id, quote_status="produzido", quote_kind="personal",
                   quote_total=Decimal("0"), cpv_calc=Decimal("70"), is_sold=False,
                   variable_costs=Decimal("0")))
        s.add(Sale(quote_id=q_vendido.id, quote_status="entregue", quote_kind="personal",
                   quote_total=Decimal("200"), cpv_calc=Decimal("40"), is_sold=True,
                   confirmed_revenue=Decimal("200"), variable_costs=Decimal("0"),
                   sold_at=date(2026, 9, 10)))

        item_perdido = QuoteItem(quote_id=q_perdido.id, name="p", gcode_meta={}, quantity=1)
        item_vendido = QuoteItem(quote_id=q_vendido.id, name="v", gcode_meta={}, quantity=1)
        spool = Spool(material_type="PLA", purchased_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
                      purchased_price=Decimal("100"), initial_grams=Decimal("1000"),
                      remaining_grams=Decimal("700"))
        s.add_all([item_perdido, item_vendido, spool])
        await s.commit()

        # A data de produção é o que atribui a linha ao período, nos dois lados.
        s.add(MaterialConsumption(quote_item_id=item_perdido.id, spool_id=spool.id,
                                  grams_used=Decimal("100"), unit_cost_snapshot=Decimal("0.50"),
                                  consumed_at=datetime(2026, 9, 12, tzinfo=timezone.utc)))
        s.add(MaterialConsumption(quote_item_id=item_vendido.id, spool_id=spool.id,
                                  grams_used=Decimal("80"), unit_cost_snapshot=Decimal("0.50"),
                                  consumed_at=datetime(2026, 9, 14, tzinfo=timezone.utc)))
        await s.commit()

    async with session_module.SessionFactory() as s:
        dre = await compute_dre(s, PERIODO_DE, PERIODO_ATE)

    # O vendido não entra na perda; só o não-vendido, pelo CPV cheio.
    assert dre["perda_operacional"] == Decimal("70.00")

    linhas = (await auth_client.get("/accounting/sales?kind=personal")).json()
    soma_aba = sum(
        (Decimal(linha["cpv_override"] or linha["cpv_calc"])
         for linha in linhas
         if not linha["is_sold"] and not linha["is_stale"]
         and linha["produced_on"] is not None
         and PERIODO_DE <= date.fromisoformat(linha["produced_on"]) <= PERIODO_ATE),
        Decimal(0),
    )
    assert soma_aba == dre["perda_operacional"], (
        f"rodapé da aba ({soma_aba}) diverge do DRE ({dre['perda_operacional']})"
    )
