"""Auto-calibration: pure-domain algorithm + types.

This package compares orçado vs real consumption to surface actionable
suggestions for adjusting MaterialVersion.failure_rate_pct and
MaterialVersion.price_per_kg_ref. NO DB imports here — the route fetches
the data and passes it to `compute_material_insights`.
"""
from backend.core.calibration.algo import (
    MIN_SAMPLE_SIZE,
    DEVIATION_THRESHOLD_PCT,
    DIAMETER_MM_DEFAULT,
    InsightDraft,
    ConsumptionFact,
    ItemFact,
    MaterialFact,
    compute_material_insights,
)

__all__ = [
    "MIN_SAMPLE_SIZE",
    "DEVIATION_THRESHOLD_PCT",
    "DIAMETER_MM_DEFAULT",
    "InsightDraft",
    "ConsumptionFact",
    "ItemFact",
    "MaterialFact",
    "compute_material_insights",
]
