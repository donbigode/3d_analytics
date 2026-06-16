from decimal import Decimal

from backend.core.gcode.parser import GcodeMeta
from backend.core.pricing.cost import grams_from_meters
from backend.core.pricing.quote import ItemInput


def effective_grams_per_unit(
    filament_m: float,
    filament_g: float | None,
    density: Decimal,
    diameter_mm: Decimal,
    waste_pct: Decimal,
) -> Decimal:
    """Gramas por peça para custo.

    Se ``filament_g`` está preenchido e > 0, é o valor final (sem refugo).
    Senão, deriva dos metros e aplica ``waste_pct``.
    """
    if filament_g is not None and filament_g > 0:
        return Decimal(str(filament_g))
    grams = grams_from_meters(filament_m, density, diameter_mm)
    if waste_pct > 0:
        grams = grams * (Decimal(100) + waste_pct) / Decimal(100)
    return grams


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
    maintenance_per_hour: Decimal = Decimal("0"),
    waste_pct: Decimal = Decimal("0"),
) -> ItemInput:
    """Build an ItemInput for cost computation from parsed gcode metadata and material/settings.

    ``waste_pct`` inflates the consumed filament to account for purges,
    brims, supports and color-change towers. The caller picks the right
    side of the material's single/multi-color presets based on the item's
    ``is_multi_color`` flag.
    """
    grams = grams_from_meters(meta.filament_m, density, diameter_mm)
    if waste_pct > 0:
        grams = grams * (Decimal(100) + waste_pct) / Decimal(100)
    return ItemInput(
        grams=grams,
        price_per_kg=price_per_kg,
        time_s=meta.time_s,
        power_w=power_w,
        kwh_price=kwh_price,
        depreciation_per_hour=depreciation_per_hour,
        failure_pct=failure_pct,
        quantity=quantity,
        maintenance_per_hour=maintenance_per_hour,
    )


def grams_for_item(meta_dict: dict, density: Decimal, quantity: int,
                   diameter_mm: Decimal = Decimal("1.75")) -> Decimal:
    """Compute total grams consumed by an item with `quantity` copies."""
    meters = float(meta_dict.get("filament_m") or 0)
    per_unit = grams_from_meters(meters, density, diameter_mm)
    return per_unit * Decimal(quantity)
