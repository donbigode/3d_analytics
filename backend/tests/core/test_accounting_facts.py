from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from backend.core.accounting.facts import compute_facts
from backend.core.models import QuoteKind, QuoteStatus
from backend.infra.db import session as session_module
from backend.infra.db.models import (
    Client, MaterialConsumption, MaterialVersion, Quote, QuoteItem, Sale, Spool, User,
)


@pytest.mark.asyncio
async def test_facts_item_grain_color_and_revenue_split():
    async with session_module.SessionFactory() as s:
        user = User(name="u", email="facts@t.com", password_hash="x")
        cli = Client(name="Ana")
        mv = MaterialVersion(material_type="PLA", name="PLA", color="Azul",
                             density_g_cm3=Decimal("1.24"), price_per_kg_ref=Decimal("100"))
        s.add_all([user, cli, mv]); await s.commit()
        q = Quote(kind=QuoteKind.COMMERCIAL.value, user_id=user.id, client_id=cli.id,
                  status=QuoteStatus.ENTREGUE.value, markup_pct=Decimal("0"), min_charge=Decimal("0"))
        s.add(q); await s.commit()
        # item 1: gramas override 50 (custo 5,00); item 2: gramas override 50 (custo 5,00)
        it1 = QuoteItem(quote_id=q.id, name="Vaso", gcode_meta={"filament_g": 50},
                        material_version_id=mv.id, quantity=2)
        it2 = QuoteItem(quote_id=q.id, name="Suporte", gcode_meta={"filament_g": 50},
                        material_version_id=mv.id, quantity=1)
        spool = Spool(material_type="PLA", color="Verde", purchased_at=datetime.now(timezone.utc),
                      purchased_price=Decimal("100"), initial_grams=Decimal("1000"),
                      remaining_grams=Decimal("900"))
        s.add_all([it1, it2, spool]); await s.commit()
        # baixa real só do item 1, da bobina Verde
        s.add(MaterialConsumption(quote_item_id=it1.id, spool_id=spool.id,
                                  grams_used=Decimal("100"), unit_cost_snapshot=Decimal("0.50"),
                                  consumed_at=datetime.now(timezone.utc)))
        s.add(Sale(quote_id=q.id, quote_status="entregue", quote_kind="commercial",
                   quote_total=Decimal("300"), cpv_calc=Decimal("50"), is_sold=True, is_stale=False,
                   confirmed_revenue=Decimal("300"), variable_costs=Decimal("0"),
                   client_id=cli.id, sold_at=date(2026, 6, 10)))
        await s.commit()

    async with session_module.SessionFactory() as s:
        rows = await compute_facts(s, date(2026, 6, 1), date(2026, 6, 30))

    assert len(rows) == 2  # uma linha por item
    by_name = {r["nome"]: r for r in rows}
    vaso = by_name["Vaso"]; sup = by_name["Suporte"]
    # venda repetida
    assert vaso["receita_venda"] == Decimal("300.00")
    assert vaso["cliente"] == "Ana"
    # item: gramas_total = 50 * qty; custo = gramas/1000 * 100
    assert vaso["quantidade"] == 2
    assert vaso["gramas_total"] == Decimal("100.00")           # 50 * 2
    assert vaso["custo_filamento_item"] == Decimal("10.00")    # 100g a R$100/kg
    assert sup["gramas_total"] == Decimal("50.00")
    assert sup["custo_filamento_item"] == Decimal("5.00")
    # cor: item 1 tem bobina Verde; item 2 não produzido -> cor_bobina nula, cor_material Azul
    assert vaso["cor_bobina"] == "Verde"
    assert sup["cor_bobina"] is None
    assert sup["cor_material"] == "Azul"
    # receita_item rateada por custo de filamento (10 vs 5 => 200 / 100) e soma = 300
    assert vaso["receita_item"] == Decimal("200.00")
    assert sup["receita_item"] == Decimal("100.00")
    assert vaso["receita_item"] + sup["receita_item"] == Decimal("300.00")
