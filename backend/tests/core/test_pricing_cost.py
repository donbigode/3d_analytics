from decimal import Decimal
from backend.core.pricing.cost import (
    depreciation_cost,
    energy_cost,
    filament_cost,
    grams_from_meters,
    maintenance_cost,
)
from backend.core.pricing.quote import ItemInput, compute_item_cost


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


def test_maintenance_cost():
    # 2h × R$ 0,50/h = R$ 1,00
    cost = maintenance_cost(time_s=7200, rate_per_hour=Decimal("0.50"))
    assert cost == Decimal("1.00")


def test_compute_item_cost_includes_maintenance():
    """End-to-end: the printer-maintenance line shows up in the final cost.
    Sanity check using round numbers — base = filament 10 + energy 0 +
    depreciation 2 + maintenance 1 = 13; failure 0%; qty 1 = 13."""
    item = ItemInput(
        grams=Decimal("100"),
        price_per_kg=Decimal("100"),
        time_s=3600,
        power_w=Decimal("0"),
        kwh_price=Decimal("0"),
        depreciation_per_hour=Decimal("2"),
        failure_pct=Decimal("0"),
        quantity=1,
        maintenance_per_hour=Decimal("1"),
    )
    assert compute_item_cost(item) == Decimal("13.00")


def test_compute_item_cost_omits_maintenance_when_absent():
    """Backwards compatibility: callers that don't pass maintenance still
    compute the same value as before."""
    item = ItemInput(
        grams=Decimal("100"),
        price_per_kg=Decimal("100"),
        time_s=3600,
        power_w=Decimal("0"),
        kwh_price=Decimal("0"),
        depreciation_per_hour=Decimal("2"),
        failure_pct=Decimal("0"),
        quantity=1,
    )
    assert compute_item_cost(item) == Decimal("12.00")


def test_gcode_to_item_input_applies_waste():
    """The refugo (waste) percentage inflates ``grams`` before cost calc.
    20% waste on 100m of PLA 1.75mm 1.24 g/cm³ ≈ 100 × 2.4053 × 1.24 ×
    1.20 = 357.91 g."""
    from backend.core.gcode.parser import GcodeMeta
    from backend.core.quote_service import gcode_to_item_input

    ii_no_waste = gcode_to_item_input(
        meta=GcodeMeta(time_s=0, filament_m=100, material=None, machine=None),
        density=Decimal("1.24"),
        price_per_kg=Decimal("100"),
        power_w=Decimal("0"),
        kwh_price=Decimal("0"),
        depreciation_per_hour=Decimal("0"),
        failure_pct=Decimal("0"),
        quantity=1,
        waste_pct=Decimal("0"),
    )
    ii_multi = gcode_to_item_input(
        meta=GcodeMeta(time_s=0, filament_m=100, material=None, machine=None),
        density=Decimal("1.24"),
        price_per_kg=Decimal("100"),
        power_w=Decimal("0"),
        kwh_price=Decimal("0"),
        depreciation_per_hour=Decimal("0"),
        failure_pct=Decimal("0"),
        quantity=1,
        waste_pct=Decimal("20"),
    )
    # 20% mais filamento por causa de purga/wipe tower
    assert ii_multi.grams == ii_no_waste.grams * Decimal("1.20")
