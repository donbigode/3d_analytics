"""OpenAI (GPT) adapter — uses the responses API with response_format=json_object."""
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


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        from openai import OpenAI  # lazy import

        self._client = OpenAI(api_key=api_key)
        self._model = model

    async def suggest_trends(
        self, *, locale: str = "pt-BR", count: int = 10
    ) -> tuple[list[SuggestionCandidate], str | None]:
        user = SUGGEST_USER_TEMPLATE.format(count=count)
        try:
            resp = await asyncio.to_thread(
                self._client.chat.completions.create,
                model=self._model,
                messages=[
                    {"role": "system", "content": SUGGEST_SYSTEM},
                    {"role": "user", "content": user},
                ],
                response_format={"type": "json_object"},
                max_tokens=1024,
            )
        except Exception as e:  # noqa: BLE001
            msg = _short_error("openai", e)
            logger.warning("openai.suggest_trends failed: %s", msg)
            return [], msg

        text = (resp.choices[0].message.content or "") if resp.choices else ""
        parsed = _parse_suggestions(text)
        if not parsed:
            return [], "openai returned no parseable candidates"
        return parsed, None

    async def synthesize_narrative(self, *, observations_summary: str) -> str | None:
        user = NARRATIVE_USER_TEMPLATE.format(observations_summary=observations_summary)
        try:
            resp = await asyncio.to_thread(
                self._client.chat.completions.create,
                model=self._model,
                messages=[
                    {"role": "system", "content": NARRATIVE_SYSTEM},
                    {"role": "user", "content": user},
                ],
                max_tokens=512,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("openai.synthesize_narrative failed: %s", e)
            return None
        if not resp.choices:
            return None
        return (resp.choices[0].message.content or "").strip() or None
