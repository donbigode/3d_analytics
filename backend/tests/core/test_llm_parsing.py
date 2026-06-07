"""Unit tests for the LLM response parser. No network."""
from backend.core.trends.llm.anthropic_provider import _parse_suggestions


def test_parse_clean_json():
    text = '{"items": [{"term": "porta celular", "rationale": "subindo"}]}'
    out = _parse_suggestions(text)
    assert len(out) == 1
    assert out[0].term == "porta celular"
    assert out[0].rationale == "subindo"


def test_parse_markdown_fenced():
    text = "```json\n{\"items\": [{\"term\": \"organizador\"}]}\n```"
    out = _parse_suggestions(text)
    assert len(out) == 1
    assert out[0].term == "organizador"
    assert out[0].rationale is None


def test_parse_garbage_returns_empty():
    assert _parse_suggestions("no json here") == []


def test_parse_skips_blank_terms():
    text = '{"items": [{"term": ""}, {"term": "ok"}, {"rationale": "no term"}]}'
    out = _parse_suggestions(text)
    assert [s.term for s in out] == ["ok"]
