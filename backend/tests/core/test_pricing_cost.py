from decimal import Decimal
from backend.core.pricing.cost import grams_from_meters, filament_cost, energy_cost, depreciation_cost


def test_grams_pla_175():
    # PLA 1.75mm, densidade 1.24 g/cm³, 1 metro
    g = grams_from_meters(meters=1.0, density_g_cm3=Decimal("1.24"), diameter_mm=Decimal("1.75"))
    assert round(g, 2) == round(Decimal("2.98"), 2)


def test_filament_cost():
    cost = filament_cost(grams=Decimal("100"), price_per_kg=Decimal("110"))
    assert cost == Decimal("11.00")


def test_energy_cost():
    # 1 hora a 150W com tarifa 0.95 R$/kWh = 0.1425
    cost = energy_cost(time_s=3600, power_w=Decimal("150"), kwh_price=Decimal("0.95"))
    assert round(cost, 4) == Decimal("0.1425")


def test_depreciation_cost():
    cost = depreciation_cost(time_s=7200, rate_per_hour=Decimal("2.50"))
    assert cost == Decimal("5.00")
