from decimal import Decimal

import pytest

from backend.core.accounting.cost import apply_markup, compute_quote_costs
from backend.infra.db import session as session_module
from backend.infra.db.models import (
    MaterialConsumption, MaterialVersion, Quote, QuoteItem, Settings, Spool, User,
)
from backend.core.models import QuoteKind, QuoteStatus
from datetime import datetime, timezone


def test_apply_markup_min_charge():
    # 100 + 50% = 150, acima do min_charge 80
    assert apply_markup(Decimal("100"), Decimal("50"), Decimal("80")) == Decimal("150")
    # 100 + 0% = 100, abaixo do min_charge 200 -> usa min
    assert apply_markup(Decimal("100"), Decimal("0"), Decimal("200")) == Decimal("200")


@pytest.mark.asyncio
async def test_compute_quote_costs_components():
    async with session_module.SessionFactory() as s:
        user = User(name="u", email="cost@t.com", password_hash="x")
        mv = MaterialVersion(material_type="PLA", name="PLA", density_g_cm3=Decimal("1.24"),
                             price_per_kg_ref=Decimal("100"))
        settings = await s.merge(Settings(id=1, energy_kwh_price=Decimal("1.00"),
                                          printer_power_w=Decimal("100"),
                                          printer_depreciation_per_hour=Decimal("0")))
        s.add_all([user, mv]); await s.commit()
        q = Quote(kind=QuoteKind.COMMERCIAL.value, user_id=user.id,
                  status=QuoteStatus.PRODUZIDO.value, markup_pct=Decimal("0"),
                  min_charge=Decimal("0"))
        s.add(q); await s.commit()
        # 10 m de filamento, 3600 s de impressão
        item = QuoteItem(quote_id=q.id, name="peça", gcode_meta={"filament_m": 10, "time_s": 3600},
                         material_version_id=mv.id, quantity=1)
        spool = Spool(material_type="PLA", purchased_at=datetime.now(timezone.utc),
                      purchased_price=Decimal("100"), initial_grams=Decimal("1000"),
                      remaining_grams=Decimal("900"))
        s.add_all([item, spool]); await s.commit()
        # consumo real: 25 g a R$0,10/g = R$2,50
        cons = MaterialConsumption(quote_item_id=item.id, spool_id=spool.id,
                                   grams_used=Decimal("25"), unit_cost_snapshot=Decimal("0.10"))
        s.add(cons); await s.commit()

        costs = await compute_quote_costs(s, q, settings)
        # energia: 100W * 1h / 1000 * R$1 = R$0,10
        assert costs.energy == Decimal("0.10")
        assert costs.real_filament == Decimal("2.50")
        assert costs.cpv == costs.real_filament + costs.energy + costs.depreciation + costs.services


@pytest.mark.asyncio
async def test_compute_quote_costs_honors_filament_g():
    async with session_module.SessionFactory() as s:
        user = User(name="u", email="grams@t.com", password_hash="x")
        mv = MaterialVersion(material_type="PLA", name="PLA", density_g_cm3=Decimal("1.24"),
                             price_per_kg_ref=Decimal("100"))
        settings = await s.merge(Settings(id=1, energy_kwh_price=Decimal("0"),
                                          printer_power_w=Decimal("0"),
                                          printer_depreciation_per_hour=Decimal("0")))
        s.add_all([user, mv]); await s.commit()
        q = Quote(kind=QuoteKind.COMMERCIAL.value, user_id=user.id,
                  status=QuoteStatus.PRODUZIDO.value, markup_pct=Decimal("0"),
                  min_charge=Decimal("0"))
        s.add(q); await s.commit()
        item = QuoteItem(quote_id=q.id, name="p",
                         gcode_meta={"filament_m": 10, "time_s": 0, "filament_g": 50},
                         material_version_id=mv.id, quantity=1)
        s.add(item); await s.commit()

        costs = await compute_quote_costs(s, q, settings)
        assert costs.catalog_filament == Decimal("5.00")


@pytest.mark.asyncio
async def test_cpv_escala_energia_e_depreciacao_com_a_quantidade():
    """Regressão: com quantity>1, energia e depreciação escalavam? Não escalavam.

    Os dois testes acima usam quantity=1, onde ×1 esconde a diferença. Este usa
    4 cópias justamente para que a asserção possa falhar: se alguém voltar a
    somar `energy_cost(time_s, ...)` sem multiplicar pela quantidade, o valor
    esperado cai a um quarto e o teste quebra.

    A referência é o caminho de pricing (`compute_item_cost`), que multiplica o
    custo inteiro — filamento, energia, depreciação — por `quantity`. Os dois
    caminhos precisam concordar sobre o mesmo orçamento: um cobra do cliente, o
    outro vira CPV no DRE.
    """
    async with session_module.SessionFactory() as s:
        user = User(name="u", email="qty@t.com", password_hash="x")
        mv = MaterialVersion(material_type="PLA", name="PLA", density_g_cm3=Decimal("1.24"),
                             price_per_kg_ref=Decimal("100"))
        settings = await s.merge(Settings(id=1, energy_kwh_price=Decimal("1.00"),
                                         printer_power_w=Decimal("100"),
                                         printer_depreciation_per_hour=Decimal("2.00")))
        s.add_all([user, mv]); await s.commit()
        q = Quote(kind=QuoteKind.COMMERCIAL.value, user_id=user.id,
                  status=QuoteStatus.PRODUZIDO.value, markup_pct=Decimal("0"),
                  min_charge=Decimal("0"))
        s.add(q); await s.commit()
        # 1h de impressão por peça, 4 cópias.
        item = QuoteItem(quote_id=q.id, name="peça", gcode_meta={"filament_m": 10, "time_s": 3600},
                         material_version_id=mv.id, quantity=4)
        s.add(item); await s.commit()

        costs = await compute_quote_costs(s, q, settings)

        # energia por peça: 100W × 1h ÷ 1000 × R$1,00 = R$0,10  ->  ×4 = R$0,40
        assert costs.energy == Decimal("0.40"), (
            f"energia nao escalou com a quantidade: {costs.energy} (esperado 0.40)"
        )
        # depreciação por peça: 1h × R$2,00 = R$2,00  ->  ×4 = R$8,00
        assert costs.depreciation == Decimal("8.00"), (
            f"depreciacao nao escalou com a quantidade: {costs.depreciation} (esperado 8.00)"
        )


@pytest.mark.asyncio
async def test_cpv_concorda_com_o_pricing_no_mesmo_item():
    """Os dois motores de custo não podem divergir sobre o mesmo item.

    `pricing/quote.py` decide o que o cliente paga; `accounting/cost.py` decide
    o CPV que vai pro DRE. Divergência entre eles é margem fantasma. Este teste
    compara os dois diretamente, com quantidade > 1 para que a assimetria de
    escala apareça.

    Compara só filamento de catálogo + energia + depreciação: o pricing ainda
    aplica `failure_pct` e `maintenance_cost`, que o contábil não aplica. Essa
    diferença é decisão de produto em aberto (provisão de falha não é custo
    realizado), não bug — e está documentada nos achados pendentes.
    """
    from backend.core.pricing.quote import ItemInput, compute_item_cost

    async with session_module.SessionFactory() as s:
        user = User(name="u", email="cmp@t.com", password_hash="x")
        mv = MaterialVersion(material_type="PLA", name="PLA", density_g_cm3=Decimal("1.24"),
                             price_per_kg_ref=Decimal("100"))
        settings = await s.merge(Settings(id=1, energy_kwh_price=Decimal("0.95"),
                                         printer_power_w=Decimal("150"),
                                         printer_depreciation_per_hour=Decimal("1.50")))
        s.add_all([user, mv]); await s.commit()
        q = Quote(kind=QuoteKind.COMMERCIAL.value, user_id=user.id,
                  status=QuoteStatus.PRODUZIDO.value, markup_pct=Decimal("0"),
                  min_charge=Decimal("0"))
        s.add(q); await s.commit()
        item = QuoteItem(quote_id=q.id, name="peça",
                         gcode_meta={"filament_m": 20, "time_s": 4 * 3600, "filament_g": 60},
                         material_version_id=mv.id, quantity=4)
        s.add(item); await s.commit()

        costs = await compute_quote_costs(s, q, settings)
        contabil = costs.catalog_filament + costs.energy + costs.depreciation

        pricing = compute_item_cost(ItemInput(
            grams=Decimal("60"), price_per_kg=Decimal("100"), time_s=4 * 3600,
            power_w=Decimal("150"), kwh_price=Decimal("0.95"),
            depreciation_per_hour=Decimal("1.50"), failure_pct=Decimal("0"), quantity=4,
        ))

        assert contabil == pricing, (
            f"contabil ({contabil}) divergiu do pricing ({pricing}) no mesmo item"
        )
