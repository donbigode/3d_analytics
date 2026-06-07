from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable


@dataclass(frozen=True)
class LaborLine:
    unit: str  # "min" | "hour" | "g"
    quantity: Decimal
    rate: Decimal


def labor_cost(lines: Iterable[LaborLine]) -> Decimal:
    total = Decimal(0)
    for ln in lines:
        total += ln.quantity * ln.rate
    return total
