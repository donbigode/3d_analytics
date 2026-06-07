"""Temporal window parsing + Google Trends timeframe mapping."""
from backend.core.trends.llm.anthropic_provider import _parse_suggestions


def test_parses_valid_window():
    text = (
        '{"items": [{"term": "x", "rationale": "y", "temporal_window": "day"}]}'
    )
    out = _parse_suggestions(text)
    assert out[0].temporal_window == "day"


def test_defaults_to_week_when_missing():
    text = '{"items": [{"term": "x", "rationale": "y"}]}'
    out = _parse_suggestions(text)
    assert out[0].temporal_window == "week"


def test_defaults_to_week_when_invalid():
    text = '{"items": [{"term": "x", "temporal_window": "yearly"}]}'
    out = _parse_suggestions(text)
    assert out[0].temporal_window == "week"


def test_accepts_all_three_windows():
    text = (
        '{"items": ['
        '{"term": "a", "temporal_window": "day"},'
        '{"term": "b", "temporal_window": "week"},'
        '{"term": "c", "temporal_window": "month"}'
        "]}"
    )
    out = _parse_suggestions(text)
    assert [s.temporal_window for s in out] == ["day", "week", "month"]
