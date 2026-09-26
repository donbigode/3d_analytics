from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

from backend.core.pricing.cost import (
    depreciation_cost,
    energy_cost,
    filament_cost,
    maintenance_cost,
)
from backend.core.pricing.failure import apply_failure


@dataclass(frozen=True)
class FilamentLine:
    """Um filamento de um item: gramas **por peça** e preço do seu material.

    Preço por linha, não por item, porque duas cores podem custar diferente —
    é justamente isso que torna a separação útil.
    """

    grams: Decimal
    price_per_kg: Decimal


@dataclass(frozen=True)
class ItemInput:
    # Um item tem N filamentos. Item de uma cor tem uma linha — não há caminho
    # separado para "cor única", porque dois caminhos divergem.
    filaments: tuple[FilamentLine, ...]
    time_s: float
    power_w: Decimal
    kwh_price: Decimal
    depreciation_per_hour: Decimal
    failure_pct: Decimal
    quantity: int
    # Optional — defaults to 0 so existing call sites that don't pass it
    # keep behaving exactly as before.
    maintenance_per_hour: Decimal = Decimal("0")


@dataclass(frozen=True)
class ServiceLine:
    quantity: Decimal
    rate: Decimal
    is_material: bool  # purga = True; labor/other = False


def compute_item_cost(item: ItemInput) -> Decimal:
    # Gramas somam por linha de filamento; time_s NÃO. O gcode descreve a
    # impressão da peça inteira, com todas as suas cores, então energia,
    # depreciação e manutenção contam o tempo UMA vez — e só depois tudo
    # escala pela quantidade de cópias.
    fil = sum(
        (filament_cost(f.grams, f.price_per_kg) for f in item.filaments), Decimal(0)
    )
    en = energy_cost(item.time_s, item.power_w, item.kwh_price)
    dep = depreciation_cost(item.time_s, item.depreciation_per_hour)
    maint = maintenance_cost(item.time_s, item.maintenance_per_hour)
    base = fil + en + dep + maint
    with_failure = apply_failure(base, item.failure_pct)
    return with_failure * Decimal(item.quantity)


def compute_quote_total(
    items: Iterable[ItemInput],
    services: Iterable[ServiceLine],
    markup_pct: Decimal,
    min_charge: Decimal,
) -> Decimal:
    items_cost = sum((compute_item_cost(i) for i in items), Decimal(0))
    services_cost = sum((s.quantity * s.rate for s in services), Decimal(0))
    cost = items_cost + services_cost
    with_markup = (cost * (Decimal(100) + markup_pct) / Decimal(100)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return max(with_markup, min_charge)
