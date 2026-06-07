"""Google Gemini adapter (google-genai SDK)."""
from __future__ import annotations

import asyncio
import logging

from backend.core.trends.llm.anthropic_provider import _parse_suggestions, _short_error
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
    ) -> tuple[list[SuggestionCandidate], str | None]:
        prompt = SUGGEST_SYSTEM + "\n\n" + SUGGEST_USER_TEMPLATE.format(count=count)

        # One retry on 429 RESOURCE_EXHAUSTED. Gemini's free tier gives back a
        # retryDelay; we use a conservative 30s cap so the request stays sync
        # from the caller's perspective.
        last_exc: Exception | None = None
        for attempt in (1, 2):
            try:
                resp = await asyncio.to_thread(
                    self._client.models.generate_content,
                    model=self._model,
                    contents=prompt,
                )
                last_exc = None
                break
            except Exception as e:  # noqa: BLE001
                last_exc = e
                if attempt == 1 and "429" in str(e) and "RESOURCE_EXHAUSTED" in str(e):
                    logger.info("gemini 429, retrying in 30s")
                    import asyncio as _a
                    await _a.sleep(30)
                    continue
                break

        if last_exc is not None:
            msg = _short_error("gemini", last_exc)
            logger.warning("gemini.suggest_trends failed: %s", msg)
            return [], msg

        text = getattr(resp, "text", "") or ""
        parsed = _parse_suggestions(text)
        if not parsed:
            return [], "gemini returned no parseable candidates"
        return parsed, None

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
