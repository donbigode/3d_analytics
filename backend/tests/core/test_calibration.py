"""Unit tests for the pure calibration algorithm."""
from decimal import Decimal

from backend.core.calibration import (
    DIAMETER_MM_DEFAULT,
    ConsumptionFact,
    ItemFact,
    MaterialFact,
    compute_material_insights,
)
from backend.core.calibration.algo import _grams_per_meter


def _pla() -> MaterialFact:
    return MaterialFact(
        material_code="PLA",
        density_g_cm3=Decimal("1.24"),
        price_per_kg_ref=Decimal("100"),
        failure_rate_pct=Decimal("0"),
    )


def _item(item_id: str, filament_m: str = "5", qty: int = 1, code: str = "PLA") -> ItemFact:
    return ItemFact(
        item_id=item_id, material_code=code, filament_m=Decimal(filament_m), quantity=qty
    )


def _grams_for(filament_m: str, density: str = "1.24") -> Decimal:
    return _grams_per_meter(Decimal(density)) * Decimal(filament_m)


def test_no_samples_returns_empty():
    out = compute_material_insights([], [], [_pla()])
    assert out == []


def test_low_sample_returns_empty():
    # Just 3 consumptions — below MIN_SAMPLE_SIZE (5).
    mat = _pla()
    items = [_item(f"i{i}") for i in range(3)]
    cons = [
        ConsumptionFact(item_id=f"i{i}", grams_used=Decimal("999"), unit_cost_snapshot=Decimal("9"))
        for i in range(3)
    ]
    out = compute_material_insights(cons, items, [mat])
    assert out == []


def test_failure_rate_deviation_surfaced():
    """5 items declared 5m each. Theoretical grams ≈ 12.02 each. We pretend
    the printer wasted ~15% extra: real grams = theoretical × 1.15. Catalog
    says failure 0% → suggestion should be ~15%."""
    mat = _pla()
    theoretical_per_item = _grams_for("5")  # grams per single item, qty=1
    real_per_item = theoretical_per_item * Decimal("1.15")

    items = [_item(f"i{i}") for i in range(6)]
    # unit_cost_snapshot matches the catalog price (100 R$/kg → 0.10 R$/g)
    # so the price insight does NOT fire.
    cons = [
        ConsumptionFact(
            item_id=f"i{i}",
            grams_used=real_per_item,
            unit_cost_snapshot=Decimal("0.10"),
        )
        for i in range(6)
    ]
    out = compute_material_insights(cons, items, [mat])

    failures = [d for d in out if d.scope_kind == "material_failure"]
    assert len(failures) == 1
    f = failures[0]
    assert f.scope_ref == "PLA"
    assert f.sample_size == 6
    # observed ≈ 15.00%, current 0%, delta ≈ 15.00
    assert abs(f.observed_value - Decimal("15.00")) < Decimal("0.05")
    assert f.current_value == Decimal("0.00")
    assert abs(f.delta_pct - Decimal("15.00")) < Decimal("0.05")
    # no price insight (real cost matches catalog)
    assert [d for d in out if d.scope_kind == "material_price"] == []


def test_small_deviation_below_threshold_is_ignored():
    """Only 1% extra waste — below the 3% threshold, should NOT surface."""
    mat = _pla()
    theoretical_per_item = _grams_for("5")
    real_per_item = theoretical_per_item * Decimal("1.01")  # 1% extra
    items = [_item(f"i{i}") for i in range(8)]
    cons = [
        ConsumptionFact(
            item_id=f"i{i}",
            grams_used=real_per_item,
            unit_cost_snapshot=Decimal("0.10"),  # matches catalog
        )
        for i in range(8)
    ]
    out = compute_material_insights(cons, items, [mat])
    assert out == []


def test_price_deviation_surfaced():
    """Catalog says R$ 100/kg → 0.10 R$/g. Reality avg 0.13 R$/g → R$ 130/kg
    (30% above). Should surface a material_price insight."""
    mat = _pla()
    theoretical_per_item = _grams_for("5")
    items = [_item(f"i{i}") for i in range(5)]
    cons = [
        ConsumptionFact(
            item_id=f"i{i}",
            grams_used=theoretical_per_item,  # no waste → no failure insight
            unit_cost_snapshot=Decimal("0.13"),
        )
        for i in range(5)
    ]
    out = compute_material_insights(cons, items, [mat])
    prices = [d for d in out if d.scope_kind == "material_price"]
    assert len(prices) == 1
    p = prices[0]
    assert p.scope_ref == "PLA"
    assert p.sample_size == 5
    assert abs(p.observed_value - Decimal("130.00")) < Decimal("0.05")
    assert p.current_value == Decimal("100.00")
    assert abs(p.delta_pct - Decimal("30.00")) < Decimal("0.05")


def test_unknown_item_or_material_skipped():
    mat = _pla()
    items = [_item("known")]
    cons = [
        ConsumptionFact(item_id="ghost", grams_used=Decimal("100"), unit_cost_snapshot=Decimal("0.1"))
        for _ in range(10)
    ]
    out = compute_material_insights(cons, items, [mat])
    assert out == []
