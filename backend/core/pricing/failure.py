from decimal import Decimal, ROUND_HALF_UP


def apply_failure(base_cost: Decimal, failure_pct: Decimal) -> Decimal:
    return (base_cost * (Decimal(100) + failure_pct) / Decimal(100)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
