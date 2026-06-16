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
    filament_g: float | None = None,
) -> ItemInput:
    """Build an ItemInput for cost computation from parsed gcode metadata and material/settings.

    ``waste_pct`` inflates the consumed filament to account for purges,
    brims, supports and color-change towers. The caller picks the right
    side of the material's single/multi-color presets based on the item's
    ``is_multi_color`` flag.

    If ``filament_g`` is provided and > 0, it is used as-is (no waste applied).
    """
    grams = effective_grams_per_unit(meta.filament_m, filament_g, density, diameter_mm, waste_pct)
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
    """Total de gramas consumidas por um item com `quantity` cópias."""
    meters = float(meta_dict.get("filament_m") or 0)
    raw_g = meta_dict.get("filament_g")
    filament_g = float(raw_g) if raw_g not in (None, "") else None
    per_unit = effective_grams_per_unit(meters, filament_g, density, diameter_mm, Decimal("0"))
    return per_unit * Decimal(quantity)
