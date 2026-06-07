import math
from decimal import Decimal


def grams_from_meters(meters: float, density_g_cm3: Decimal, diameter_mm: Decimal) -> Decimal:
    area_mm2 = Decimal(str(math.pi)) * (diameter_mm / 2) ** 2
    # meters * (area mm² * density g/cm³) → area mm² × 1m = 1000 mm³ = 1 cm³ × density
    grams_per_m = area_mm2 * density_g_cm3
    return Decimal(str(meters)) * grams_per_m


def filament_cost(grams: Decimal, price_per_kg: Decimal) -> Decimal:
    return (grams / Decimal(1000)) * price_per_kg


def energy_cost(time_s: float, power_w: Decimal, kwh_price: Decimal) -> Decimal:
    hours = Decimal(str(time_s)) / Decimal(3600)
    kwh = power_w * hours / Decimal(1000)
    return kwh * kwh_price


def depreciation_cost(time_s: float, rate_per_hour: Decimal) -> Decimal:
    hours = Decimal(str(time_s)) / Decimal(3600)
    return hours * rate_per_hour
