"""Abstract LLM provider interface."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SuggestionCandidate:
    """One keyword candidate emitted by an LLM."""

    term: str
    rationale: str | None = None


class LLMProvider(Protocol):
    """Provider contract.

    Implementations must be safe to call from async code (use ``asyncio.to_thread``
    if the underlying SDK is sync) and must NOT raise on transient errors — they
    return empty lists and let the caller log via DataSourceRun.
    """

    name: str

    async def suggest_trends(self, *, locale: str = "pt-BR", count: int = 10) -> list[SuggestionCandidate]:
        ...

    async def synthesize_narrative(self, *, observations_summary: str) -> str | None:
        """Optional: returns a short paragraph summarizing the state of the radar.

        Implementations can return ``None`` if the provider isn't configured or
        the call fails. The caller persists the narrative as a DataSourceRun
        metadata field — there's no dedicated table for narratives in the MVP.
        """
        ...
