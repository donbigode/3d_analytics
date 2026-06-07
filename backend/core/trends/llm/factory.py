"""Pick the right LLM provider based on Settings."""
from __future__ import annotations

from backend.core.trends.llm.base import LLMProvider


def _make(name: str, *, anthropic_key: str | None, gemini_key: str | None) -> LLMProvider | None:
    if name == "anthropic" and anthropic_key:
        from backend.core.trends.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider(api_key=anthropic_key)
    if name == "gemini" and gemini_key:
        from backend.core.trends.llm.gemini_provider import GeminiProvider

        return GeminiProvider(api_key=gemini_key)
    return None


def resolve_provider(
    *, preferred: str, anthropic_key: str | None, gemini_key: str | None
) -> LLMProvider | None:
    """Return a single provider for the preferred slot, or None."""
    return _make(preferred, anthropic_key=anthropic_key, gemini_key=gemini_key) or _make(
        "anthropic" if preferred != "anthropic" else "gemini",
        anthropic_key=anthropic_key,
        gemini_key=gemini_key,
    )


def resolve_chain(
    *, preferred: str, anthropic_key: str | None, gemini_key: str | None
) -> list[LLMProvider]:
    """Return providers to try in order — preferred first, fallback second.

    Used by the scheduler so a paid-quota outage on one provider doesn't kill
    the whole collection: we transparently fall back to the other.
    """
    order = [preferred, "anthropic" if preferred != "anthropic" else "gemini"]
    chain: list[LLMProvider] = []
    for name in order:
        p = _make(name, anthropic_key=anthropic_key, gemini_key=gemini_key)
        if p is not None and p not in chain:
            chain.append(p)
    return chain
