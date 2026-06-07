"""Pick the right LLM provider based on Settings."""
from __future__ import annotations

from backend.core.trends.llm.base import LLMProvider


def resolve_provider(
    *, preferred: str, anthropic_key: str | None, gemini_key: str | None
) -> LLMProvider | None:
    """Return a configured provider or ``None`` if no keys are set.

    Falls back to the alternate provider if the preferred one has no key.
    """
    # Try preferred first.
    if preferred == "anthropic" and anthropic_key:
        from backend.core.trends.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider(api_key=anthropic_key)
    if preferred == "gemini" and gemini_key:
        from backend.core.trends.llm.gemini_provider import GeminiProvider

        return GeminiProvider(api_key=gemini_key)
    # Fallback: try whichever key exists.
    if anthropic_key:
        from backend.core.trends.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider(api_key=anthropic_key)
    if gemini_key:
        from backend.core.trends.llm.gemini_provider import GeminiProvider

        return GeminiProvider(api_key=gemini_key)
    return None
