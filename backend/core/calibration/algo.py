"""Calibration algorithm — pure, no DB.

Compares real consumption (from MaterialConsumption rows) against:
  - the theoretical grams declared by the gcode (per-item filament_m × density),
  - the catalog reference price (MaterialVersion.price_per_kg_ref).

Produces a list of InsightDraft rows; the route persists them.

Time-accuracy calibration is INTENTIONALLY skipped for MVP: we don't track
actual production duration today (no print start/end timestamps on
MaterialConsumption). Add it once the produce flow records `duration_s`.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable


# ---------- tunables ----------

MIN_SAMPLE_SIZE: int = 5  # minimum produced items per material to surface
DEVIATION_THRESHOLD_PCT: Decimal = Decimal("3")  # |delta%| must exceed this
DIAMETER_MM_DEFAULT: Decimal = Decimal("1.75")
_PI = Decimal("3.14159265358979323846")


# ---------- fact DTOs (pure data, no SQLAlchemy) ----------

@dataclass(frozen=True)
class MaterialFact:
    material_code: str
    density_g_cm3: Decimal
    price_per_kg_ref: Decimal
    failure_rate_pct: Decimal


@dataclass(frozen=True)
class ItemFact:
    item_id: str
    material_code: str
    filament_m: Decimal       # declared by gcode (per single unit)
    quantity: int


@dataclass(frozen=True)
class ConsumptionFact:
    item_id: str
    grams_used: Decimal       # real grams debited from a spool
    unit_cost_snapshot: Decimal  # R$ / g (spool.purchased_price / spool.initial_grams)


@dataclass(frozen=True)
class InsightDraft:
    scope_kind: str      # "material_failure" | "material_price"
    scope_ref: str       # material_code
    observed_value: Decimal
    current_value: Decimal
    suggested_value: Decimal
    delta_pct: Decimal
    sample_size: int


# ---------- helpers ----------

def _grams_per_meter(density_g_cm3: Decimal, diameter_mm: Decimal = DIAMETER_MM_DEFAULT) -> Decimal:
    """Filament mass per meter: π/4 × d² × density. Units: g per meter (d in mm = cm² mm²?).

    With d in mm, area = π/4 × d² [mm²]. 1 meter of filament = 1000 mm length.
    Volume per meter = area × 1000 mm³ = area cm³ (since 1000 mm³ = 1 cm³).
    Mass = volume × density [g/cm³].
    """
    area_mm2 = (_PI / Decimal(4)) * (diameter_mm * diameter_mm)
    # 1m of filament volume in cm³ = area_mm² × 1000 mm / 1000 = area_mm²/1
    # (since 1000 mm³ = 1 cm³). So grams/m = area_mm² × density.
    return area_mm2 * density_g_cm3


def _q(d: Decimal, places: str = "0.01") -> Decimal:
    return d.quantize(Decimal(places), rounding=ROUND_HALF_UP)


# ---------- main entry ----------

def compute_material_insights(
    consumptions: Iterable[ConsumptionFact],
    items: Iterable[ItemFact],
    materials: Iterable[MaterialFact],
    *,
    min_sample_size: int = MIN_SAMPLE_SIZE,
    deviation_threshold_pct: Decimal = DEVIATION_THRESHOLD_PCT,
    diameter_mm: Decimal = DIAMETER_MM_DEFAULT,
) -> list[InsightDraft]:
    """Pure: returns one or two InsightDrafts per material that meets the
    sample-size + deviation thresholds.

    `material_failure`: observed = (real_grams / theoretical_grams) - 1
        compared to current failure_rate_pct/100 (as a multiplier).
    `material_price`:   observed = mean(unit_cost_snapshot) × 1000 [R$/kg]
        compared to MaterialVersion.price_per_kg_ref [R$/kg].

    Both thresholds: |delta_pct| > deviation_threshold_pct, sample >= min_sample_size.
    """
    items_by_id: dict[str, ItemFact] = {it.item_id: it for it in items}
    mat_by_code: dict[str, MaterialFact] = {m.material_code: m for m in materials}

    # group consumptions by material
    per_mat_real: dict[str, Decimal] = {}
    per_mat_theoretical: dict[str, Decimal] = {}
    per_mat_unit_cost_sum: dict[str, Decimal] = {}
    per_mat_n: dict[str, int] = {}

    for c in consumptions:
        it = items_by_id.get(c.item_id)
        if it is None:
            continue
        mat = mat_by_code.get(it.material_code)
        if mat is None:
            continue
        code = mat.material_code
        gpm = _grams_per_meter(mat.density_g_cm3, diameter_mm)
        theoretical = gpm * it.filament_m * Decimal(it.quantity)
        if theoretical <= 0:
            continue
        per_mat_real[code] = per_mat_real.get(code, Decimal(0)) + c.grams_used
        per_mat_theoretical[code] = per_mat_theoretical.get(code, Decimal(0)) + theoretical
        per_mat_unit_cost_sum[code] = (
            per_mat_unit_cost_sum.get(code, Decimal(0)) + c.unit_cost_snapshot
        )
        per_mat_n[code] = per_mat_n.get(code, 0) + 1

    out: list[InsightDraft] = []

    for code, n in per_mat_n.items():
        if n < min_sample_size:
            continue
        mat = mat_by_code[code]
        real_g = per_mat_real[code]
        theo_g = per_mat_theoretical[code]
        if theo_g <= 0:
            continue

        # ----- failure rate -----
        # observed extra ratio: real / theoretical - 1 (in %)
        observed_failure_pct = (real_g / theo_g - Decimal(1)) * Decimal(100)
        current_failure_pct = Decimal(mat.failure_rate_pct)
        delta = observed_failure_pct - current_failure_pct
        # Use absolute deviation in percentage *points* — matches the unit
        # users think in ("failure went from 5% to 12% → +7 pts").
        if abs(delta) > deviation_threshold_pct:
            out.append(
                InsightDraft(
                    scope_kind="material_failure",
                    scope_ref=code,
                    observed_value=_q(observed_failure_pct, "0.01"),
                    current_value=_q(current_failure_pct, "0.01"),
                    suggested_value=_q(observed_failure_pct, "0.01"),
                    delta_pct=_q(delta, "0.01"),
                    sample_size=n,
                )
            )

        # ----- price per kg -----
        mean_unit_cost = per_mat_unit_cost_sum[code] / Decimal(n)  # R$/g
        observed_price_per_kg = mean_unit_cost * Decimal(1000)
        current_price = Decimal(mat.price_per_kg_ref)
        if current_price > 0:
            price_delta_pct = (observed_price_per_kg - current_price) / current_price * Decimal(100)
            if abs(price_delta_pct) > deviation_threshold_pct:
                out.append(
                    InsightDraft(
                        scope_kind="material_price",
                        scope_ref=code,
                        observed_value=_q(observed_price_per_kg, "0.01"),
                        current_value=_q(current_price, "0.01"),
                        suggested_value=_q(observed_price_per_kg, "0.01"),
                        delta_pct=_q(price_delta_pct, "0.01"),
                        sample_size=n,
                    )
                )

    return out
