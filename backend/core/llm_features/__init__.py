"""LLM-powered features that read your real data.

Each module here builds a focused prompt from the DB and asks the configured
provider chain (Anthropic → Gemini → OpenAI) for a structured response. The
shared :func:`call_text` / :func:`call_json` helpers handle provider selection,
fallback, and error reporting; individual modules only build context + parse.
"""
from backend.core.llm_features.runner import LLMUnavailable, call_json, call_text

__all__ = ["call_text", "call_json", "LLMUnavailable"]
