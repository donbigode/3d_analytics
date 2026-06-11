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


async def _invoke(
    provider,
    *,
    system: str,
    user: str,
    max_tokens: int,
    enable_web_search: bool = False,
    max_searches: int = 5,
) -> tuple[str | None, str | None, list[dict]]:
    """Hit a single provider's underlying SDK.

    Returns ``(text, error, citations)`` where ``citations`` is a list of
    ``{url, title}`` dicts collected from the LLM's tool-use blocks when
    ``enable_web_search=True`` (Anthropic only). Other providers ignore
    ``enable_web_search`` for now and the citations list comes back empty.
    """
    citations: list[dict] = []
    try:
        if provider.name == "anthropic":
            kwargs: dict = dict(
                model=provider._model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            if enable_web_search:
                kwargs["tools"] = [
                    {
                        "type": "web_search_20250305",
                        "name": "web_search",
                        "max_uses": max_searches,
                    }
                ]
            resp = await asyncio.to_thread(
                provider._client.messages.create, **kwargs
            )
            text_parts: list[str] = []
            seen_urls: set[str] = set()
            for b in resp.content:
                if getattr(b, "type", None) == "text":
                    text_parts.append(getattr(b, "text", "") or "")
                    # Each text block may carry citations from web_search.
                    for c in getattr(b, "citations", None) or []:
                        url = getattr(c, "url", None) or (c.get("url") if isinstance(c, dict) else None)
                        title = getattr(c, "title", None) or (
                            c.get("title") if isinstance(c, dict) else None
                        )
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            citations.append({"url": url, "title": title})
            text = "".join(text_parts)
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
            return None, f"provider {provider.name} not supported", citations
        return text.strip() or None, None, citations
    except Exception as exc:  # noqa: BLE001
        return None, f"{provider.name}: {str(exc)[:200]}", citations


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
        text, err, _ = await _invoke(
            provider, system=system, user=user, max_tokens=max_tokens
        )
        if text:
            return text
        if err:
            errors.append(err)
    raise LLMUnavailable("; ".join(errors) or "empty response from all providers")


async def call_json_with_research(
    session: AsyncSession,
    *,
    system: str,
    user: str,
    max_tokens: int = 1500,
    max_searches: int = 5,
) -> tuple[dict[str, Any], list[dict]]:
    """Like :func:`call_json` but enables web search on the Anthropic provider.

    Other providers in the chain fall back to a regular text call (no search).
    Returns ``(parsed_json, citations)`` where each citation is
    ``{url: str, title: str | None}``.

    Use this for features where you want the LLM to actively look up prices
    on Mercado Livre, Shopee, Amazon BR and similar pages rather than
    relying on a single pre-fetched API result.
    """
    chain, reason = await _build_chain(session)
    if not chain:
        raise LLMUnavailable(reason or "no provider")
    errors: list[str] = []
    for provider in chain:
        text, err, citations = await _invoke(
            provider,
            system=system,
            user=user,
            max_tokens=max_tokens,
            enable_web_search=(provider.name == "anthropic"),
            max_searches=max_searches,
        )
        if text:
            return _parse_json_or_raise(text), citations
        if err:
            errors.append(err)
    raise LLMUnavailable("; ".join(errors) or "empty response from all providers")


def _parse_json_or_raise(raw: str) -> dict[str, Any]:
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
    return _parse_json_or_raise(raw)
