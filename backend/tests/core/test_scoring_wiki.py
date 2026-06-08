"""Scoring with Wikipedia fallback."""
from decimal import Decimal

from backend.core.trends.scoring import score


def test_wiki_used_when_interest_is_missing():
    # No Google Trends interest, but Wikipedia has views.
    s_with = score(None, None, None, wiki_views=Decimal("1000"))
    s_without = score(None, None, None)
    assert s_with > s_without


def test_google_trends_takes_precedence_over_wiki():
    # When both are present, interest path dominates (50-band weight).
    s_with_gt = score(Decimal("80"), None, None, wiki_views=Decimal("1000"))
    s_only_wiki = score(None, None, None, wiki_views=Decimal("1000"))
    assert s_with_gt > s_only_wiki


def test_wiki_zero_contributes_nothing():
    assert score(None, None, None, wiki_views=Decimal("0")) == Decimal("0.00")


def test_full_signal_bounds():
    # All three signals at max -> close to 100.
    s = score(Decimal("100"), Decimal("10000"), Decimal("200"))
    assert s > Decimal("95")
    assert s <= Decimal("100.00")


def test_wikipedia_log_normalization_caps():
    # Very large wiki value should still cap around 50 (the interest band).
    big = score(None, None, None, wiki_views=Decimal("100000"))
    fits = score(None, None, None, wiki_views=Decimal("10000"))
    # 100k > ceiling (10k) but log normalization caps both near 50.
    assert big <= Decimal("50.00")
    assert fits <= Decimal("50.00")
