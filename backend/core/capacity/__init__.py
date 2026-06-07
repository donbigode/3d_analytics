"""Capacity / schedule forecast (Wave 5 Lane F2).

Pure-domain code: zero framework, zero DB. Only standard library + Decimal +
datetime. Input is a list of summarized queue jobs (one entry per approved
quote), output is a Forecast object summarizing the next-available window and
per-quote ETAs.
"""

from backend.core.capacity.forecast import (
    Forecast,
    ForecastJob,
    QuoteSummary,
    compute_forecast,
)

__all__ = ["Forecast", "ForecastJob", "QuoteSummary", "compute_forecast"]
