"""Shared LLM caller for the feature modules.

Builds on top of the existing :mod:`backend.core.trends.llm` provider chain
(Anthropic → Gemini → OpenAI). Two entry points:

  - :func:`call_text` — for prose responses (digest, variance explanation)
  - :func:`call_json` — for structured responses (auto-name, markup, variants)

Both honour the user's preferred_llm_provider and fall through to the others
if quota / auth fails on the first.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.trends.llm import resolve_chain
from backend.infra.db.models import Settings

logger = logging.getLogger(__name__)


class LLMUnavailable(Exception):
    """No provider in the chain returned a usable response."""


async def _build_chain(session: AsyncSession):
    settings_row = await session.get(Settings, 1)
    if settings_row is None:
        return [], "no settings row"
    chain = resolve_chain(
        preferred=settings_row.preferred_llm_provider,
        anthropic_key=settings_row.anthropic_api_key,
        gemini_key=settings_row.gemini_api_key,
        openai_key=settings_row.openai_api_key,
    )
    if not chain:
        return [], "nenhum provider LLM configurado em /config"
    return chain, None


async def _invoke(provider, *, system: str, user: str, max_tokens: int) -> tuple[str | None, str | None]:
    """Hit a single provider's underlying SDK. Returns (text, error)."""
    try:
        if provider.name == "anthropic":
            resp = await asyncio.to_thread(
                provider._client.messages.create,
                model=provider._model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            text = "".join(b.text for b in resp.content if b.type == "text")
        elif provider.name == "openai":
            resp = await asyncio.to_thread(
                provider._client.chat.completions.create,
                model=provider._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=max_tokens,
            )
            text = (resp.choices[0].message.content or "") if resp.choices else ""
        elif provider.name == "gemini":
            prompt = f"{system}\n\n{user}"
            resp = await asyncio.to_thread(
                provider._client.models.generate_content,
                model=provider._model,
                contents=prompt,
            )
            text = getattr(resp, "text", "") or ""
        else:
            return None, f"provider {provider.name} not supported"
        return text.strip() or None, None
    except Exception as exc:  # noqa: BLE001
        return None, f"{provider.name}: {str(exc)[:200]}"


async def call_text(
    session: AsyncSession,
    *,
    system: str,
    user: str,
    max_tokens: int = 600,
) -> str:
    """Run the provider chain until one succeeds. Raise :class:`LLMUnavailable`
    when all providers fail.
    """
    chain, reason = await _build_chain(session)
    if not chain:
        raise LLMUnavailable(reason or "no provider")
    errors: list[str] = []
    for provider in chain:
        text, err = await _invoke(provider, system=system, user=user, max_tokens=max_tokens)
        if text:
            return text
        if err:
            errors.append(err)
    raise LLMUnavailable("; ".join(errors) or "empty response from all providers")


async def call_json(
    session: AsyncSession,
    *,
    system: str,
    user: str,
    max_tokens: int = 800,
) -> dict[str, Any]:
    """Like :func:`call_text` but parses the response as JSON.

    The prompt is expected to ask for JSON-only output; we strip ```json fences
    and find the outermost {...} block as a fallback.
    """
    raw = await call_text(session, system=system, user=user, max_tokens=max_tokens)
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            raise LLMUnavailable("response was not JSON")
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise LLMUnavailable(f"JSON parse failed: {exc}") from exc
