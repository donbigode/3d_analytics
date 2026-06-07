from decimal import Decimal

from backend.core.trends.scoring import score


def test_all_none_yields_zero():
    assert score(None, None, None) == Decimal("0.00")


def test_only_interest_max():
    # 100/100 * 50 = 50.00
    s = score(Decimal("100"), None, None)
    assert s == Decimal("50.00")


def test_only_volume_high():
    # log10(1+10000) hits the ceiling -> 40.00 exactly
    s = score(None, Decimal("10000"), None)
    assert s == Decimal("40.00")


def test_only_price():
    # 100/200 * 10 = 5.00
    s = score(None, None, Decimal("100"))
    assert s == Decimal("5.00")


def test_full_signal_caps_at_100():
    # interest 100 + huge volume + huge price -> 50 + 40 + 10 = 100
    s = score(Decimal("100"), Decimal("9999999"), Decimal("9999"))
    assert s == Decimal("100.00")


def test_interest_clamped_negative():
    # negative interest should not subtract score (clamped to 0)
    s = score(Decimal("-5"), None, None)
    assert s == Decimal("0.00")


def test_zero_volume_doesnt_contribute():
    s = score(Decimal("50"), Decimal("0"), Decimal("0"))
    # only interest contributes: 50/100 * 50 = 25
    assert s == Decimal("25.00")


def test_ordering_higher_signal_higher_score():
    a = score(Decimal("80"), Decimal("500"), Decimal("60"))
    b = score(Decimal("20"), Decimal("5"), Decimal("10"))
    assert a > b
