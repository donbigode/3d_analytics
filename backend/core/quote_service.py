from decimal import Decimal

from backend.core.gcode.parser import GcodeMeta
from backend.core.pricing.cost import grams_from_meters
from backend.core.pricing.quote import ItemInput


def gcode_to_item_input(
    meta: GcodeMeta,
    density: Decimal,
    price_per_kg: Decimal,
    power_w: Decimal,
    kwh_price: Decimal,
    depreciation_per_hour: Decimal,
    failure_pct: Decimal,
    quantity: int,
    diameter_mm: Decimal = Decimal("1.75"),
) -> ItemInput:
    """Build an ItemInput for cost computation from parsed gcode metadata and material/settings."""
    grams = grams_from_meters(meta.filament_m, density, diameter_mm)
    return ItemInput(
        grams=grams,
        price_per_kg=price_per_kg,
        time_s=meta.time_s,
        power_w=power_w,
        kwh_price=kwh_price,
        depreciation_per_hour=depreciation_per_hour,
        failure_pct=failure_pct,
        quantity=quantity,
    )


def grams_for_item(meta_dict: dict, density: Decimal, quantity: int,
                   diameter_mm: Decimal = Decimal("1.75")) -> Decimal:
    """Compute total grams consumed by an item with `quantity` copies."""
    meters = float(meta_dict.get("filament_m") or 0)
    per_unit = grams_from_meters(meters, density, diameter_mm)
    return per_unit * Decimal(quantity)
