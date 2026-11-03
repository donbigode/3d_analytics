"""Pick the right LLM provider based on Settings."""
from __future__ import annotations

import logging

from backend.core.trends.llm.base import LLMProvider

logger = logging.getLogger(__name__)

ALL_PROVIDERS = ("anthropic", "gemini", "openai")


def _make(
    name: str,
    *,
    anthropic_key: str | None,
    gemini_key: str | None,
    openai_key: str | None,
) -> LLMProvider | None:
    """Build one provider, or None if it has no key or its SDK isn't installed.

    Production installs without the ``ai`` extra (pyproject.toml), so a key
    saved in /config may point at an SDK that isn't there. Skipping it lets
    every caller fall into its existing "no provider configured" path instead
    of a 500.
    """
    try:
        if name == "anthropic" and anthropic_key:
            from backend.core.trends.llm.anthropic_provider import AnthropicProvider

            return AnthropicProvider(api_key=anthropic_key)
        if name == "gemini" and gemini_key:
            from backend.core.trends.llm.gemini_provider import GeminiProvider

            return GeminiProvider(api_key=gemini_key)
        if name == "openai" and openai_key:
            from backend.core.trends.llm.openai_provider import OpenAIProvider

            return OpenAIProvider(api_key=openai_key)
    except ImportError as e:
        logger.warning("LLM provider %s skipped: SDK not installed (%s)", name, e)
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
