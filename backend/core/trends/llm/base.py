"""Abstract LLM provider interface."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SuggestionCandidate:
    """One keyword candidate emitted by an LLM.

    `temporal_window` is one of ``day | week | month`` and drives the
    Google Trends timeframe in the downstream collection step:
      - day   → last 1 day
      - week  → last 7 days
      - month → last 30 days
    Defaults to 'week' when the LLM omits or returns a value we don't recognise.
    """

    term: str
    rationale: str | None = None
    temporal_window: str = "week"


class LLMProvider(Protocol):
    """Provider contract.

    Implementations are safe from async code (use ``asyncio.to_thread`` if the
    underlying SDK is sync) and never raise. They return a tuple of
    ``(candidates, error)`` — when ``error`` is not None, the scheduler logs a
    failed DataSourceRun with that message instead of pretending success.
    """

    name: str

    async def suggest_trends(
        self, *, locale: str = "pt-BR", count: int = 10
    ) -> tuple[list[SuggestionCandidate], str | None]:
        ...

    async def synthesize_narrative(self, *, observations_summary: str) -> str | None:
        """Optional: returns a short paragraph summarizing the state of the radar.

        Implementations can return ``None`` if the provider isn't configured or
        the call fails. The caller persists the narrative as a DataSourceRun
        metadata field — there's no dedicated table for narratives in the MVP.
        """
        ...
