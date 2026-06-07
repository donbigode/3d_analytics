"""Google Gemini adapter (google-genai SDK)."""
from __future__ import annotations

import asyncio
import logging

from backend.core.trends.llm.anthropic_provider import _parse_suggestions
from backend.core.trends.llm.base import LLMProvider, SuggestionCandidate
from backend.core.trends.llm.prompts import (
    NARRATIVE_SYSTEM,
    NARRATIVE_USER_TEMPLATE,
    SUGGEST_SYSTEM,
    SUGGEST_USER_TEMPLATE,
)

logger = logging.getLogger(__name__)


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash") -> None:
        from google import genai  # lazy import

        self._client = genai.Client(api_key=api_key)
        self._model = model

    async def suggest_trends(
        self, *, locale: str = "pt-BR", count: int = 10
    ) -> list[SuggestionCandidate]:
        prompt = SUGGEST_SYSTEM + "\n\n" + SUGGEST_USER_TEMPLATE.format(count=count)
        try:
            resp = await asyncio.to_thread(
                self._client.models.generate_content,
                model=self._model,
                contents=prompt,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("gemini.suggest_trends failed: %s", e)
            return []
        text = getattr(resp, "text", "") or ""
        return _parse_suggestions(text)

    async def synthesize_narrative(self, *, observations_summary: str) -> str | None:
        prompt = (
            NARRATIVE_SYSTEM
            + "\n\n"
            + NARRATIVE_USER_TEMPLATE.format(observations_summary=observations_summary)
        )
        try:
            resp = await asyncio.to_thread(
                self._client.models.generate_content,
                model=self._model,
                contents=prompt,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("gemini.synthesize_narrative failed: %s", e)
            return None
        return (getattr(resp, "text", "") or "").strip() or None
