"""LLM provider abstraction for the trend radar.

Two providers are supported out of the box: Anthropic (Claude) and Google
Gemini. Each implements :class:`LLMProvider` and is hand-picked at runtime
based on Settings.preferred_llm_provider + the corresponding API key.
"""
from backend.core.trends.llm.base import LLMProvider, SuggestionCandidate
from backend.core.trends.llm.factory import resolve_chain, resolve_provider

__all__ = [
    "LLMProvider",
    "SuggestionCandidate",
    "resolve_provider",
    "resolve_chain",
]
