from decimal import Decimal
from backend.core.pricing.labor import labor_cost, LaborLine
from backend.core.pricing.failure import apply_failure
from backend.core.pricing.quote import compute_item_cost, compute_quote_total, ItemInput, ServiceLine


def test_labor_cost_minute():
    line = LaborLine(unit="min", quantity=Decimal("15"), rate=Decimal("1.20"))
    assert labor_cost([line]) == Decimal("18.00")


def test_apply_failure():
    base = Decimal("100")
    assert apply_failure(base, failure_pct=Decimal("5")) == Decimal("105.00")


def test_compute_quote_total_commercial():
    item = ItemInput(
        grams=Decimal("50"), price_per_kg=Decimal("100"),
        time_s=3600, power_w=Decimal("150"), kwh_price=Decimal("1.0"),
        depreciation_per_hour=Decimal("2.0"), failure_pct=Decimal("0"),
        quantity=1,
    )
    services = [ServiceLine(quantity=Decimal("10"), rate=Decimal("1.0"), is_material=False)]
    total = compute_quote_total(items=[item], services=services, markup_pct=Decimal("50"), min_charge=Decimal("0"))
    # filament: 50g * 100/1000 = 5; energy: 1h*150W*1.0 = 0.15; deprec: 2.0; failure: 0%; labor: 10
    # cost = 5 + 0.15 + 2.0 + 10 = 17.15 → markup 50% → 25.725
    assert round(total, 2) == Decimal("25.73")


def test_min_charge_floor():
    item = ItemInput(grams=Decimal("1"), price_per_kg=Decimal("100"),
                     time_s=60, power_w=Decimal("100"), kwh_price=Decimal("1.0"),
                     depreciation_per_hour=Decimal("0"), failure_pct=Decimal("0"), quantity=1)
    total = compute_quote_total(items=[item], services=[], markup_pct=Decimal("0"), min_charge=Decimal("50"))
    assert total == Decimal("50.00")
