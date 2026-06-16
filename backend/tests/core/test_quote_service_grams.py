from decimal import Decimal

from backend.core.quote_service import effective_grams_per_unit

_D = Decimal("1.75")


def test_override_wins_no_waste():
    g = effective_grams_per_unit(filament_m=10.0, filament_g=25.0,
                                 density=Decimal("1.24"), diameter_mm=_D,
                                 waste_pct=Decimal("20"))
    assert g == Decimal("25")


def test_no_override_derives_with_waste():
    base = effective_grams_per_unit(filament_m=10.0, filament_g=None,
                                    density=Decimal("1.24"), diameter_mm=_D,
                                    waste_pct=Decimal("0"))
    withw = effective_grams_per_unit(filament_m=10.0, filament_g=None,
                                     density=Decimal("1.24"), diameter_mm=_D,
                                     waste_pct=Decimal("10"))
    assert base > 0
    assert withw == base * Decimal("110") / Decimal("100")


def test_zero_grams_falls_back_to_meters():
    g0 = effective_grams_per_unit(filament_m=10.0, filament_g=0.0,
                                  density=Decimal("1.24"), diameter_mm=_D,
                                  waste_pct=Decimal("0"))
    gm = effective_grams_per_unit(filament_m=10.0, filament_g=None,
                                  density=Decimal("1.24"), diameter_mm=_D,
                                  waste_pct=Decimal("0"))
    assert g0 == gm


from backend.core.quote_service import gcode_to_item_input
from backend.core.gcode.parser import GcodeMeta
from backend.core.pricing.quote import compute_item_cost


def test_item_input_uses_grams_override():
    meta = GcodeMeta(time_s=0.0, filament_m=10.0, material=None, machine=None)
    ii = gcode_to_item_input(
        meta=meta, density=Decimal("1.24"), price_per_kg=Decimal("100"),
        power_w=Decimal("0"), kwh_price=Decimal("0"), depreciation_per_hour=Decimal("0"),
        failure_pct=Decimal("0"), quantity=1, waste_pct=Decimal("20"),
        filament_g=50.0,
    )
    assert compute_item_cost(ii) == Decimal("5.00")
