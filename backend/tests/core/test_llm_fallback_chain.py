"""Provider chain ordering — preferred first, others as fallback."""
from backend.core.trends.llm.factory import resolve_chain


def test_chain_only_anthropic_when_only_key_set():
    chain = resolve_chain(
        preferred="anthropic",
        anthropic_key="sk-ant-1",
        gemini_key=None,
        openai_key=None,
    )
    names = [p.name for p in chain]
    assert names == ["anthropic"]


def test_chain_orders_preferred_first():
    chain = resolve_chain(
        preferred="gemini",
        anthropic_key="sk-ant-1",
        gemini_key="AIza-1",
        openai_key="sk-1",
    )
    names = [p.name for p in chain]
    assert names[0] == "gemini"
    assert set(names) == {"anthropic", "gemini", "openai"}
    assert len(names) == 3


def test_chain_skips_missing_keys():
    chain = resolve_chain(
        preferred="openai",
        anthropic_key=None,
        gemini_key="AIza-1",
        openai_key="sk-1",
    )
    names = [p.name for p in chain]
    assert names == ["openai", "gemini"]


def test_chain_empty_when_no_keys():
    chain = resolve_chain(
        preferred="anthropic",
        anthropic_key=None,
        gemini_key=None,
        openai_key=None,
    )
    assert chain == []


def test_chain_falls_back_when_preferred_key_missing():
    # Preferred is openai but no openai key set; chain should still surface
    # the other providers' instances in fallback order.
    chain = resolve_chain(
        preferred="openai",
        anthropic_key="sk-ant-1",
        gemini_key="AIza-1",
        openai_key=None,
    )
    names = [p.name for p in chain]
    assert names == ["anthropic", "gemini"]
