"""Anthropic Claude adapter."""
from __future__ import annotations

import asyncio
import json
import logging

from backend.core.trends.llm.base import LLMProvider, SuggestionCandidate
from backend.core.trends.llm.prompts import (
    NARRATIVE_SYSTEM,
    NARRATIVE_USER_TEMPLATE,
    SUGGEST_SYSTEM,
    SUGGEST_USER_TEMPLATE,
)

logger = logging.getLogger(__name__)


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, api_key: str, model: str = "claude-haiku-4-5-20251001") -> None:
        from anthropic import Anthropic  # imported lazily so tests w/o key don't break

        self._client = Anthropic(api_key=api_key)
        self._model = model

    async def suggest_trends(
        self, *, locale: str = "pt-BR", count: int = 10
    ) -> tuple[list[SuggestionCandidate], str | None]:
        user = SUGGEST_USER_TEMPLATE.format(count=count)
        try:
            resp = await asyncio.to_thread(
                self._client.messages.create,
                model=self._model,
                max_tokens=1024,
                system=SUGGEST_SYSTEM,
                messages=[{"role": "user", "content": user}],
            )
        except Exception as e:  # noqa: BLE001
            msg = _short_error("anthropic", e)
            logger.warning("anthropic.suggest_trends failed: %s", msg)
            return [], msg

        text = "".join(block.text for block in resp.content if block.type == "text")
        parsed = _parse_suggestions(text)
        if not parsed:
            return [], "anthropic returned no parseable candidates"
        return parsed, None

    async def synthesize_narrative(self, *, observations_summary: str) -> str | None:
        user = NARRATIVE_USER_TEMPLATE.format(observations_summary=observations_summary)
        try:
            resp = await asyncio.to_thread(
                self._client.messages.create,
                model=self._model,
                max_tokens=512,
                system=NARRATIVE_SYSTEM,
                messages=[{"role": "user", "content": user}],
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("anthropic.synthesize_narrative failed: %s", e)
            return None
        return "".join(block.text for block in resp.content if block.type == "text").strip() or None


def _short_error(provider: str, exc: Exception) -> str:
    """Compact, user-facing error message — strips stack noise."""
    body = str(exc)
    # SDKs often nest the useful bit in a message field; pull it out when present.
    for marker in ("'message':", '"message":'):
        if marker in body:
            tail = body.split(marker, 1)[1]
            # Strip leading whitespace/quotes and stop at the next quote.
            tail = tail.lstrip(" '\"")
            end = tail.find("'")
            if end == -1:
                end = tail.find('"')
            if end > 0:
                return f"{provider}: {tail[:end]}"
    # Generic fallback: first 200 chars.
    return f"{provider}: {body[:200]}"


_VALID_WINDOWS = {"day", "week", "month"}


def _parse_suggestions(text: str) -> list[SuggestionCandidate]:
    """Best-effort JSON parsing of suggestion responses."""
    text = text.strip()
    # The LLM might wrap with ```json ... ``` fences
    if text.startswith("```"):
        text = text.strip("`")
        # leading 'json' marker
        if text.startswith("json"):
            text = text[4:]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Last-resort: find the first {...} block
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            return []
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return []
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    out: list[SuggestionCandidate] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        term = (it.get("term") or "").strip()
        if not term:
            continue
        rationale = (it.get("rationale") or "").strip() or None
        window = (it.get("temporal_window") or "").strip().lower()
        if window not in _VALID_WINDOWS:
            window = "week"
        out.append(
            SuggestionCandidate(
                term=term, rationale=rationale, temporal_window=window
            )
        )
    return out
