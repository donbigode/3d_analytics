"""Opportunity score for a keyword idea.

Heuristic, intentionally simple and tunable later:

    score = 50 * normalized_interest
          + 40 * log_volume
          + 10 * normalized_price

Where:
    normalized_interest = interest / 100                 (Google Trends is 0-100)
    log_volume          = log10(1 + ml_volume) / log10(1 + 10000)   (clipped to 1.0)
    normalized_price    = min(ml_avg_price, 200) / 200   (R$, capped at 200)

Each weight contributes 0..1 of its own band, so the final score is in 0..100.
Missing signals are treated as zero contribution (so a keyword with no data at
all scores 0).
"""

from __future__ import annotations

import math
from decimal import Decimal


_VOLUME_CEILING = math.log10(1 + 10_000)
_WIKI_CEILING = math.log10(1 + 10_000)   # 10k mean daily views = saturated
_PRICE_CEILING = Decimal("200")


def score(
    interest: Decimal | None,
    ml_volume: Decimal | None,
    ml_avg_price: Decimal | None,
    *,
    wiki_views: Decimal | None = None,
) -> Decimal:
    """Combine the signals into a 0..100 opportunity score.

    Interest source: Google Trends if available, otherwise log-normalized
    Wikipedia pageviews (PT-BR) as a free fallback. See module docstring.
    """

    interest_part = Decimal("0")
    if interest is not None:
        clipped = max(Decimal("0"), min(Decimal("100"), Decimal(interest)))
        interest_part = (clipped / Decimal("100")) * Decimal("50")
    elif wiki_views is not None and wiki_views > 0:
        # Log-scale 0..1 then weight to 50.
        log_w = math.log10(1 + float(wiki_views)) / _WIKI_CEILING
        log_w = min(1.0, max(0.0, log_w))
        interest_part = Decimal(str(log_w)) * Decimal("50")

    volume_part = Decimal("0")
    if ml_volume is not None and ml_volume > 0:
        log_v = math.log10(1 + float(ml_volume)) / _VOLUME_CEILING
        log_v = min(1.0, max(0.0, log_v))
        volume_part = Decimal(str(log_v)) * Decimal("40")

    price_part = Decimal("0")
    if ml_avg_price is not None and ml_avg_price > 0:
        capped = min(Decimal(ml_avg_price), _PRICE_CEILING)
        price_part = (capped / _PRICE_CEILING) * Decimal("10")

    total = interest_part + volume_part + price_part
    return total.quantize(Decimal("0.01"))
