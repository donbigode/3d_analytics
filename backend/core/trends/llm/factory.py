"""Pick the right LLM provider based on Settings."""
from __future__ import annotations

from backend.core.trends.llm.base import LLMProvider

ALL_PROVIDERS = ("anthropic", "gemini", "openai")


def _make(
    name: str,
    *,
    anthropic_key: str | None,
    gemini_key: str | None,
    openai_key: str | None,
) -> LLMProvider | None:
    if name == "anthropic" and anthropic_key:
        from backend.core.trends.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider(api_key=anthropic_key)
    if name == "gemini" and gemini_key:
        from backend.core.trends.llm.gemini_provider import GeminiProvider

        return GeminiProvider(api_key=gemini_key)
    if name == "openai" and openai_key:
        from backend.core.trends.llm.openai_provider import OpenAIProvider

        return OpenAIProvider(api_key=openai_key)
    return None


def resolve_provider(
    *,
    preferred: str,
    anthropic_key: str | None,
    gemini_key: str | None,
    openai_key: str | None = None,
) -> LLMProvider | None:
    """Return a single configured provider (preferred first, else any other)."""
    chain = resolve_chain(
        preferred=preferred,
        anthropic_key=anthropic_key,
        gemini_key=gemini_key,
        openai_key=openai_key,
    )
    return chain[0] if chain else None


def resolve_chain(
    *,
    preferred: str,
    anthropic_key: str | None,
    gemini_key: str | None,
    openai_key: str | None = None,
) -> list[LLMProvider]:
    """Return providers to try in order — preferred first, then the rest.

    Used by the scheduler so a paid-quota outage on one provider doesn't kill
    the whole collection: we transparently fall back to the next available.
    """
    order = [preferred] + [p for p in ALL_PROVIDERS if p != preferred]
    chain: list[LLMProvider] = []
    for name in order:
        p = _make(
            name,
            anthropic_key=anthropic_key,
            gemini_key=gemini_key,
            openai_key=openai_key,
        )
        if p is not None:
            chain.append(p)
    return chain
