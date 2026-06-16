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
